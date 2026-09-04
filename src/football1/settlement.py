from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football1.live_odds import API_BASE, SPORT_KEY, _safe_error_body
from football1.prospective import prediction_content_hash


DEFAULT_DAYS_FROM = 3
LABELS = ("home", "draw", "away")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_scores(
    api_key: str,
    *,
    event_ids: list[str],
    days_from: int = DEFAULT_DAYS_FROM,
    timeout: int = 30,
) -> tuple[list[dict[str, Any]], dict[str, int | None], str]:
    """Fetch live/recent EPL scores for specified provider event ids.

    The Odds API charges 2 usage credits when daysFrom is supplied. This
    function should therefore only be called when unresolved predictions exist.
    """
    if not api_key.strip():
        raise ValueError("API key is empty")
    if not event_ids:
        return [], {"requests_remaining": None, "requests_used": None, "requests_last": 0}, _utc_now()
    if days_from not in (1, 2, 3):
        raise ValueError("days_from must be 1, 2 or 3")

    query = urllib.parse.urlencode(
        {
            "apiKey": api_key,
            "daysFrom": days_from,
            "dateFormat": "iso",
            "eventIds": ",".join(sorted(set(event_ids))),
        }
    )
    url = f"{API_BASE}/sports/{SPORT_KEY}/scores/?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Football1Research/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            headers = response.headers
    except urllib.error.HTTPError as exc:
        body = _safe_error_body(exc.read())
        raise RuntimeError(f"The Odds API scores endpoint returned HTTP {exc.code}: {body}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"The Odds API scores request failed: {exc.reason}") from None

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The Odds API scores endpoint returned invalid JSON") from exc
    if not isinstance(payload, list):
        raise ValueError("Expected The Odds API scores response to be a list")

    usage: dict[str, int | None] = {}
    for key, header in (
        ("requests_remaining", "x-requests-remaining"),
        ("requests_used", "x-requests-used"),
        ("requests_last", "x-requests-last"),
    ):
        value = headers.get(header)
        try:
            usage[key] = int(value) if value is not None else None
        except ValueError:
            usage[key] = None
    return payload, usage, _utc_now()


def _load_predictions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        record_id = str(item.get("record_id", ""))
        if not record_id or record_id in seen:
            raise ValueError(f"Invalid or duplicate prediction record_id on line {line_number}")
        unsigned = dict(item)
        stored = unsigned.pop("content_sha256", None)
        if stored != prediction_content_hash(unsigned):
            raise ValueError(f"Prediction ledger line {line_number} failed content hash verification")
        seen.add(record_id)
        rows.append(item)
    return rows


def settlement_content_hash(record_without_hash: dict[str, Any]) -> str:
    encoded = json.dumps(record_without_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_settlements(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    seen_prediction_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        prediction_id = str(item.get("prediction_record_id", ""))
        if not prediction_id or prediction_id in seen_prediction_ids:
            raise ValueError(f"Invalid or duplicate settlement prediction id on line {line_number}")
        unsigned = dict(item)
        stored = unsigned.pop("content_sha256", None)
        if stored != settlement_content_hash(unsigned):
            raise ValueError(f"Settlement line {line_number} failed content hash verification")
        seen_prediction_ids.add(prediction_id)
        rows.append(item)
    return rows


def _final_score(score_event: dict[str, Any], prediction: dict[str, Any]) -> tuple[int, int]:
    if score_event.get("completed") is not True:
        raise ValueError("Cannot settle an event that is not marked completed")
    scores = score_event.get("scores")
    if not isinstance(scores, list):
        raise ValueError("Completed score event has no scores list")
    by_team = {str(row.get("name")): row.get("score") for row in scores if isinstance(row, dict)}
    home = str(prediction["home_team_provider"])
    away = str(prediction["away_team_provider"])
    try:
        return int(by_team[home]), int(by_team[away])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Score response does not contain numeric scores for {home} vs {away}") from exc


def _brier(probability: dict[str, float], result_label: str) -> float:
    return sum((float(probability[label]) - (1.0 if label == result_label else 0.0)) ** 2 for label in LABELS)


def make_settlement_record(
    prediction: dict[str, Any],
    score_event: dict[str, Any],
    *,
    scores_retrieved_at_utc: str,
) -> dict[str, Any]:
    if str(score_event.get("id")) != str(prediction["event_id"]):
        raise ValueError("Score event id does not match prediction event id")
    home_score, away_score = _final_score(score_event, prediction)
    result_label = "home" if home_score > away_score else "away" if away_score > home_score else "draw"

    market_probability = prediction["market_anchor"]["probability"]
    model_probability = prediction["model"]["probability"]
    best_odds = prediction["market_anchor"]["best_decimal_odds"]
    market_p = float(market_probability[result_label])
    model_p = float(model_probability[result_label])
    if market_p <= 0 or model_p <= 0:
        raise ValueError("Cannot score non-positive realized-outcome probability")

    unit_pnl_if_bet = {
        label: (float(best_odds[label]) - 1.0) if label == result_label else -1.0
        for label in LABELS
    }
    selected = str(prediction["model"]["max_predicted_ev_outcome"])
    if selected not in LABELS:
        raise ValueError("Prediction has invalid max_predicted_ev_outcome")

    seed = f"{prediction['record_id']}|{score_event['id']}|{home_score}-{away_score}".encode("utf-8")
    record: dict[str, Any] = {
        "schema_version": 1,
        "settlement_id": hashlib.sha256(seed).hexdigest()[:24],
        "prediction_record_id": prediction["record_id"],
        "prediction_content_sha256": prediction["content_sha256"],
        "event_id": prediction["event_id"],
        "scores_retrieved_at_utc": scores_retrieved_at_utc,
        "provider_last_update": score_event.get("last_update"),
        "home_team_provider": prediction["home_team_provider"],
        "away_team_provider": prediction["away_team_provider"],
        "home_score": home_score,
        "away_score": away_score,
        "result": result_label,
        "market_log_loss": -math.log(market_p),
        "model_log_loss": -math.log(model_p),
        "market_brier": _brier(market_probability, result_label),
        "model_brier": _brier(model_probability, result_label),
        "unit_pnl_if_bet_at_recorded_best_odds": unit_pnl_if_bet,
        "recorded_max_ev_outcome": selected,
        "recorded_max_ev": prediction["model"]["max_predicted_ev"],
        "recorded_max_ev_selection_unit_pnl": unit_pnl_if_bet[selected],
        "strategy_threshold": None,
    }
    record["content_sha256"] = settlement_content_hash(record)
    return record


def append_settlements(path: Path, records: list[dict[str, Any]]) -> int:
    existing = _load_settlements(path)
    settled_ids = {str(row["prediction_record_id"]) for row in existing}
    new_records = [row for row in records if str(row["prediction_record_id"]) not in settled_ids]
    if not new_records:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in new_records:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return len(new_records)


def settle_from_scores(
    predictions: list[dict[str, Any]],
    existing_settlements: list[dict[str, Any]],
    score_events: list[dict[str, Any]],
    *,
    scores_retrieved_at_utc: str,
) -> list[dict[str, Any]]:
    settled_ids = {str(row["prediction_record_id"]) for row in existing_settlements}
    completed_by_id = {
        str(event.get("id")): event
        for event in score_events
        if event.get("completed") is True
    }
    records: list[dict[str, Any]] = []
    for prediction in predictions:
        if str(prediction["record_id"]) in settled_ids:
            continue
        event = completed_by_id.get(str(prediction["event_id"]))
        if event is None:
            continue
        records.append(
            make_settlement_record(
                prediction,
                event,
                scores_retrieved_at_utc=scores_retrieved_at_utc,
            )
        )
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Settle locked Football 1 prospective predictions from provider scores.")
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--settlements", type=Path, default=Path("prospective/settlements.jsonl"))
    parser.add_argument("--days-from", type=int, default=DEFAULT_DAYS_FROM)
    parser.add_argument("--timeout", type=int, default=30)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    predictions = _load_predictions(args.ledger)
    existing = _load_settlements(args.settlements)
    settled_ids = {str(row["prediction_record_id"]) for row in existing}
    unresolved = [row for row in predictions if str(row["record_id"]) not in settled_ids]
    event_ids = sorted({str(row["event_id"]) for row in unresolved})
    if not event_ids:
        print("No unsettled prediction records; no scores API request made")
        return

    api_key = os.environ.get("THE_ODDS_API_KEY", "")
    if not api_key:
        raise SystemExit("THE_ODDS_API_KEY is not set")
    score_events, usage, retrieved = fetch_scores(
        api_key,
        event_ids=event_ids,
        days_from=args.days_from,
        timeout=args.timeout,
    )
    records = settle_from_scores(
        predictions,
        existing,
        score_events,
        scores_retrieved_at_utc=retrieved,
    )
    appended = append_settlements(args.settlements, records)
    print(
        json.dumps(
            {
                "unsettled_prediction_records_before": len(unresolved),
                "queried_event_ids": len(event_ids),
                "completed_events_returned": sum(event.get("completed") is True for event in score_events),
                "settlements_appended": appended,
                "scores_retrieved_at_utc": retrieved,
                "usage": usage,
            },
            sort_keys=True,
        )
    )
    for record in records:
        print(
            record["home_team_provider"], "vs", record["away_team_provider"],
            f"{record['home_score']}-{record['away_score']}",
            "model_LL=", round(float(record["model_log_loss"]), 6),
            "market_LL=", round(float(record["market_log_loss"]), 6),
            "maxEV_selection_PnL=", record["recorded_max_ev_selection_unit_pnl"],
        )


if __name__ == "__main__":
    main()
