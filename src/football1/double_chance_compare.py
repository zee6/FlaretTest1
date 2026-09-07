from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from football1.opportunity_layer import DECISION_WEIGHT, analyze_locked_prediction


COVERS = ("1X", "X2")


def _latest_locked_by_event(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("status") != "prediction_locked":
            continue
        event_id = str(record.get("event_id") or "")
        if not event_id:
            continue
        retrieved = str(record.get("snapshot_retrieved_at_utc") or "")
        current = latest.get(event_id)
        if current is None or retrieved > str(current.get("snapshot_retrieved_at_utc") or ""):
            latest[event_id] = record
    return latest


def _double_chance_by_event(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in snapshot.get("summary", []):
        if not isinstance(item, Mapping):
            continue
        event_id = str(item.get("event_id") or "")
        if event_id:
            result[event_id] = item
    return result


def _valid_odds(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 1.0:
        return None
    return price


def compare_event(
    prediction_record: Mapping[str, Any],
    double_chance_summary: Mapping[str, Any],
) -> dict[str, Any]:
    observation = analyze_locked_prediction(prediction_record)
    best = double_chance_summary.get("best_decimal_odds")
    if not isinstance(best, Mapping):
        raise ValueError("Double-chance summary is missing best_decimal_odds")

    covers: dict[str, Any] = {}
    for cover_id, observation_key in (("1X", "home_or_draw"), ("X2", "away_or_draw")):
        base = observation["non_loss"][observation_key]
        quoted = _valid_odds(best.get(cover_id))
        model_probability = float(base["model_probability"])
        synthetic = float(base["synthetic_dutched_odds"])
        covers[cover_id] = {
            "model_probability": model_probability,
            "market_probability_from_h2h": float(base["market_probability"]),
            "fair_odds": float(base["fair_odds"]),
            "synthetic_dutched_odds": synthetic,
            "model_ev_at_synthetic_odds": float(base["model_ev_at_synthetic_odds"]),
            "quoted_double_chance_odds": quoted,
            "model_ev_at_quoted_double_chance": (
                model_probability * quoted - 1.0 if quoted is not None else None
            ),
            "quoted_minus_synthetic_odds": quoted - synthetic if quoted is not None else None,
        }

    comparable = [
        (cover_id, details)
        for cover_id, details in covers.items()
        if details["model_ev_at_quoted_double_chance"] is not None
    ]
    best_quoted = None
    if comparable:
        cover_id, details = max(
            comparable,
            key=lambda item: float(item[1]["model_ev_at_quoted_double_chance"]),
        )
        best_quoted = {
            "id": cover_id,
            "model_ev_at_quoted_double_chance": details["model_ev_at_quoted_double_chance"],
            "quoted_double_chance_odds": details["quoted_double_chance_odds"],
            "fair_odds": details["fair_odds"],
        }

    return {
        "schema_version": 1,
        "event_id": prediction_record.get("event_id"),
        "source_record_id": prediction_record.get("record_id"),
        "commence_time_utc": prediction_record.get("commence_time_utc"),
        "home_team": prediction_record.get("home_team_provider"),
        "away_team": prediction_record.get("away_team_provider"),
        "status": "research_observer_zero_weight",
        "decision_weight": DECISION_WEIGHT,
        "double_chance_bookmaker_count": double_chance_summary.get("complete_bookmaker_count"),
        "covers": covers,
        "best_quoted_non_loss": best_quoted,
        "betting_threshold": None,
        "stake_rule": None,
        "warning": (
            "Quoted double-chance EV is a model diagnostic only. No materiality threshold, staking rule, "
            "or historical equivalence to the H/D/A backtest has been validated."
        ),
    }


def compare_snapshots(
    prediction_records: Iterable[dict[str, Any]],
    double_chance_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    predictions = _latest_locked_by_event(prediction_records)
    quotes = _double_chance_by_event(double_chance_snapshot)
    common = sorted(set(predictions) & set(quotes))
    rows = [compare_event(predictions[event_id], quotes[event_id]) for event_id in common]
    return {
        "schema_version": 1,
        "status": "research_observer_zero_weight",
        "decision_weight": DECISION_WEIGHT,
        "prediction_event_count": len(predictions),
        "double_chance_event_count": len(quotes),
        "common_event_count": len(rows),
        "double_chance_retrieved_at_utc": double_chance_snapshot.get("retrieved_at_utc"),
        "rows": rows,
        "warning": (
            "This joins immutable Football 1 prediction locks to an optional later/parallel double-chance "
            "snapshot by provider event ID. Timing must be inspected before any economic interpretation."
        ),
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on ledger line {line_number}") from exc
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare Football 1 non-loss fair prices with quoted double-chance odds.")
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument(
        "--double-chance-snapshot",
        type=Path,
        default=Path("data/live/epl_double_chance_snapshot.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/double_chance_compare.json"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    predictions = _load_jsonl(args.ledger)
    snapshot = json.loads(args.double_chance_snapshot.read_text(encoding="utf-8"))
    report = compare_snapshots(predictions, snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"common_event_count": report["common_event_count"], "decision_weight": DECISION_WEIGHT}, sort_keys=True))


if __name__ == "__main__":
    main()
