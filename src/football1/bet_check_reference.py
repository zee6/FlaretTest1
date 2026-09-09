from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping

from football1.price_shopping_audit import EXCHANGE_KEYS
from football1.prospective import MODEL_ALPHA, build_prospective_records


OUTCOMES = ("home", "draw", "away")


def _sportsbook_best(event_summary: Mapping[str, Any], outcome: str, *, snapshot_time: str) -> dict[str, Any] | None:
    quote_board = event_summary.get("quote_board")
    if not isinstance(quote_board, Mapping):
        return None
    raw_quotes = quote_board.get(outcome)
    if not isinstance(raw_quotes, list):
        return None

    eligible: list[dict[str, Any]] = []
    for quote in raw_quotes:
        if not isinstance(quote, Mapping):
            continue
        key = str(quote.get("bookmaker_key") or "")
        if not key or key in EXCHANGE_KEYS:
            continue
        try:
            odds = float(quote["decimal_odds"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(odds) or odds <= 1.0:
            continue
        eligible.append(
            {
                "odds": odds,
                "bookmaker_key": key,
                "bookmaker_title": str(quote.get("bookmaker_title") or key),
                "observed_at_utc": snapshot_time,
                "bookmaker_last_update": quote.get("bookmaker_last_update"),
                "market_last_update": quote.get("market_last_update"),
            }
        )
    if not eligible:
        return None
    eligible.sort(key=lambda row: (-float(row["odds"]), str(row["bookmaker_title"])))
    best = dict(eligible[0])
    best["books_checked"] = len(eligible)
    return best


def reference_from_synchronized_record(
    prediction_record: Mapping[str, Any],
    event_summary: Mapping[str, Any],
    *,
    snapshot_retrieved_at_utc: str,
) -> dict[str, Any]:
    """Join model/market probabilities and sportsbook price from one snapshot.

    This is a strict timing join. It deliberately refuses to attach a later
    quote board to an earlier Football 1 probability record.
    """
    record_event_id = str(prediction_record.get("event_id") or "")
    event_id = str(event_summary.get("event_id") or "")
    if not record_event_id or record_event_id != event_id:
        raise ValueError("Prediction and event summary event_id do not match")
    record_time = str(prediction_record.get("snapshot_retrieved_at_utc") or "")
    if not record_time or record_time != snapshot_retrieved_at_utc:
        raise ValueError("Prediction and quote board are not from the same snapshot timestamp")

    market_anchor = prediction_record.get("market_anchor")
    model = prediction_record.get("model")
    if not isinstance(market_anchor, Mapping) or not isinstance(model, Mapping):
        raise ValueError("Prediction record is missing market_anchor or model")
    market_probability = market_anchor.get("probability")
    model_probability = model.get("probability")
    if not isinstance(market_probability, Mapping) or not isinstance(model_probability, Mapping):
        raise ValueError("Prediction record is missing probability triples")

    best = {
        outcome: _sportsbook_best(event_summary, outcome, snapshot_time=snapshot_retrieved_at_utc)
        for outcome in OUTCOMES
    }
    sportsbook_counts = [
        int(value["books_checked"])
        for value in best.values()
        if isinstance(value, Mapping) and value.get("books_checked") is not None
    ]

    return {
        "schema_version": 1,
        "status": "synchronized_bet_check_reference",
        "event_id": event_id,
        "snapshot_retrieved_at_utc": snapshot_retrieved_at_utc,
        "commence_time_utc": prediction_record.get("commence_time_utc"),
        "home_team": prediction_record.get("home_team_provider") or event_summary.get("home_team"),
        "away_team": prediction_record.get("away_team_provider") or event_summary.get("away_team"),
        "market_probability": {outcome: float(market_probability[outcome]) for outcome in OUTCOMES},
        "football1_probability": {outcome: float(model_probability[outcome]) for outcome in OUTCOMES},
        "best_observed_price": best,
        "sportsbook_price_universe": {
            "known_exchange_keys_excluded": sorted(EXCHANGE_KEYS),
            "min_complete_sportsbooks_checked": min(sportsbook_counts) if sportsbook_counts else 0,
            "max_complete_sportsbooks_checked": max(sportsbook_counts) if sportsbook_counts else 0,
        },
        "source_model": {
            "id": model.get("id"),
            "alpha": model.get("alpha"),
            "market_anchor_type": market_anchor.get("type"),
        },
        "timing_contract": {
            "model_market_snapshot_timestamp": record_time,
            "best_price_snapshot_timestamp": snapshot_retrieved_at_utc,
            "exact_timestamp_match": True,
        },
        "governance": {
            "recomputed_probability_for_best_price": False,
            "raw_exchange_price_used_as_sportsbook_best": False,
            "ledger_write_required": False,
        },
    }


def build_synchronized_bet_check_references(
    db_path: Path,
    snapshot: Mapping[str, Any],
    *,
    alpha: float = MODEL_ALPHA,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snapshot_time = str(snapshot.get("retrieved_at_utc") or "")
    if not snapshot_time:
        raise ValueError("Snapshot is missing retrieved_at_utc")
    summary = snapshot.get("summary")
    if not isinstance(summary, list):
        raise ValueError("Snapshot is missing summary list")
    summaries: dict[str, Mapping[str, Any]] = {}
    for event in summary:
        if not isinstance(event, Mapping):
            continue
        event_id = str(event.get("event_id") or "")
        if not event_id:
            continue
        summaries[event_id] = event

    # Reuse the frozen prospective model path in read-only mode. This creates
    # current records but does not append them to prospective/ledger.jsonl.
    records, prospective_metadata = build_prospective_records(Path(db_path), dict(snapshot), alpha=alpha)
    references: list[dict[str, Any]] = []
    for record in records:
        event_id = str(record.get("event_id") or "")
        event = summaries.get(event_id)
        if event is None:
            raise ValueError(f"Snapshot summary missing event used by prospective model: {event_id}")
        references.append(
            reference_from_synchronized_record(
                record,
                event,
                snapshot_retrieved_at_utc=snapshot_time,
            )
        )
    references.sort(key=lambda row: (str(row.get("commence_time_utc")), str(row["event_id"])))
    metadata = {
        "status": "synchronized_bet_check_reference_set",
        "snapshot_retrieved_at_utc": snapshot_time,
        "references": len(references),
        "ledger_written": False,
        "prospective_model_metadata": prospective_metadata,
        "best_price_universe": "sportsbook_only_known_exchanges_excluded",
        "market_anchor_policy_unchanged": True,
        "warning": (
            "This bridge intentionally preserves the existing prospective market/model anchor. "
            "Known exchanges are excluded only from the executable best-sportsbook price field; "
            "changing the market consensus universe would be a separate governed experiment."
        ),
    }
    return references, metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build synchronized read-only Bet Check reference data from one live EPL snapshot.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/processed/bet_check_references.json"))
    parser.add_argument("--alpha", type=float, default=MODEL_ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    references, metadata = build_synchronized_bet_check_references(
        args.database,
        snapshot,
        alpha=args.alpha,
    )
    payload = {"metadata": metadata, "events": references}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
