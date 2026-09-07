from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from football1.opportunity_layer import DECISION_WEIGHT, analyze_locked_prediction


def _candidate(
    record: dict[str, Any],
    observation: dict[str, Any],
    *,
    category: str,
    outcome: str | None = None,
    score: float | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "source_record_id": record.get("record_id"),
        "event_id": record.get("event_id"),
        "commence_time_utc": record.get("commence_time_utc"),
        "home_team": record.get("home_team_provider"),
        "away_team": record.get("away_team_provider"),
        "outcome": outcome,
        "ranking_score": score,
        "result_call": observation["price"]["result_call"],
        "best_price_outcome": observation["price"]["best_price_outcome"],
        "result_plus_price_raw_interest": observation["price"]["result_plus_price_raw_interest"],
        "draw_shape_inputs": observation["draw_shape_inputs"],
        "outsider_non_loss": observation["non_loss"]["outsider_non_loss"],
    }


def _latest_by_event(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("status") != "prediction_locked":
            continue
        event_id = str(record.get("event_id") or "")
        retrieved = str(record.get("snapshot_retrieved_at_utc") or "")
        if not event_id:
            continue
        current = latest.get(event_id)
        if current is None or retrieved > str(current.get("snapshot_retrieved_at_utc") or ""):
            latest[event_id] = record
    return sorted(
        latest.values(),
        key=lambda record: (str(record.get("commence_time_utc") or ""), str(record.get("event_id") or "")),
    )


def build_slate_rankings(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Rank useful research views across a fixture slate without inventing recommendations."""
    slate = _latest_by_event(records)
    if not slate:
        return {
            "schema_version": 1,
            "status": "research_observer_zero_weight",
            "decision_weight": DECISION_WEIGHT,
            "fixture_count": 0,
            "rankings": {},
            "warning": "No locked prediction records were available.",
        }

    paired: list[tuple[dict[str, Any], dict[str, Any]]] = [
        (record, analyze_locked_prediction(record)) for record in slate
    ]

    def max_pair(key):
        return max(paired, key=lambda item: key(item[0], item[1]))

    def min_pair(key):
        return min(paired, key=lambda item: key(item[0], item[1]))

    # Strongest result probability, irrespective of price.
    result_record, result_obs = max_pair(
        lambda _r, o: float(o["price"]["result_call_probability"])
    )
    strongest_result_call = _candidate(
        result_record,
        result_obs,
        category="strongest_result_call",
        outcome=result_obs["price"]["result_call"],
        score=float(result_obs["price"]["result_call_probability"]),
    )

    # Best pure price discrepancy across all H/D/A outcomes.
    price_record, price_obs = max_pair(
        lambda _r, o: float(o["price"]["best_price_model_ev"])
    )
    best_price_discrepancy = _candidate(
        price_record,
        price_obs,
        category="best_price_discrepancy",
        outcome=price_obs["price"]["best_price_outcome"],
        score=float(price_obs["price"]["best_price_model_ev"]),
    )

    # Preferred class: model's most likely result also has the best raw price support.
    result_price_pairs = [
        pair for pair in paired if pair[1]["price"]["result_plus_price_raw_interest"]
    ]
    strongest_result_plus_price = None
    if result_price_pairs:
        rp_record, rp_obs = max(
            result_price_pairs,
            key=lambda item: float(item[1]["price"]["result_plus_price_model_ev"]),
        )
        strongest_result_plus_price = _candidate(
            rp_record,
            rp_obs,
            category="strongest_result_plus_price_raw_interest",
            outcome=rp_obs["price"]["result_call"],
            score=float(rp_obs["price"]["result_plus_price_model_ev"]),
        )

    # Draw as a slate-relative candidate, not H/D/A argmax.
    draw_record, draw_obs = max_pair(
        lambda _r, o: float(o["draw_shape_inputs"]["model_draw_probability"])
    )
    highest_draw_probability = _candidate(
        draw_record,
        draw_obs,
        category="highest_draw_probability",
        outcome="draw",
        score=float(draw_obs["draw_shape_inputs"]["model_draw_probability"]),
    )

    uplift_record, uplift_obs = max_pair(
        lambda _r, o: float(o["draw_shape_inputs"]["draw_probability_edge_vs_market"])
    )
    highest_draw_uplift_vs_market = _candidate(
        uplift_record,
        uplift_obs,
        category="highest_draw_uplift_vs_market",
        outcome="draw",
        score=float(uplift_obs["draw_shape_inputs"]["draw_probability_edge_vs_market"]),
    )

    # Most balanced H/A model shape; useful as a transparent draw-profile ingredient.
    balance_record, balance_obs = min_pair(
        lambda _r, o: float(o["draw_shape_inputs"]["absolute_model_home_away_gap"])
    )
    most_balanced_match = _candidate(
        balance_record,
        balance_obs,
        category="most_balanced_match",
        outcome=None,
        score=float(balance_obs["draw_shape_inputs"]["absolute_model_home_away_gap"]),
    )

    non_loss_record, non_loss_obs = max_pair(
        lambda _r, o: float(o["non_loss"]["outsider_non_loss"]["model_ev_at_synthetic_odds"])
    )
    outsider_non_loss = non_loss_obs["non_loss"]["outsider_non_loss"]
    strongest_outsider_non_loss = _candidate(
        non_loss_record,
        non_loss_obs,
        category="strongest_outsider_non_loss",
        outcome=str(outsider_non_loss["id"]),
        score=float(outsider_non_loss["model_ev_at_synthetic_odds"]),
    )

    return {
        "schema_version": 1,
        "status": "research_observer_zero_weight",
        "decision_weight": DECISION_WEIGHT,
        "fixture_count": len(paired),
        "rankings": {
            "strongest_result_call": strongest_result_call,
            "strongest_result_plus_price_raw_interest": strongest_result_plus_price,
            "best_price_discrepancy": best_price_discrepancy,
            "highest_draw_probability": highest_draw_probability,
            "highest_draw_uplift_vs_market": highest_draw_uplift_vs_market,
            "most_balanced_match": most_balanced_match,
            "strongest_outsider_non_loss": strongest_outsider_non_loss,
        },
        "interface_status": "data_contract_ready_interface_deferred",
        "warning": (
            "These are slate-relative research rankings, not betting recommendations. A category always "
            "having a 'winner' does not mean that winner clears a validated materiality threshold."
        ),
    }


def load_ledger(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on ledger line {line_number}") from exc
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank zero-weight Football 1 research views across a fixture slate.")
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/slate_rankings.json"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_slate_rankings(load_ledger(args.ledger))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"fixture_count": report["fixture_count"], "rankings": report["rankings"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
