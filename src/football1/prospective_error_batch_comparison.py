from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football1.prospective import prediction_content_hash
from football1.prospective_error_anatomy import _pair_rows, _summary
from football1.settlement import settlement_content_hash


LOCKED_SNAPSHOT_UTC = "2026-09-04T09:20:03.134040+00:00"

BATCHES: tuple[dict[str, Any], ...] = (
    {
        "batch_id": "first_settled_2026_09_04_to_06",
        "start_utc": "2026-09-04T00:00:00+00:00",
        "end_exclusive_utc": "2026-09-07T00:00:00+00:00",
        "expected_prediction_records": 10,
        "prospective_status_at_definition": "already_settled_diagnostic_reference",
    },
    {
        "batch_id": "confirmation_2026_09_12_to_14",
        "start_utc": "2026-09-12T00:00:00+00:00",
        "end_exclusive_utc": "2026-09-15T00:00:00+00:00",
        "expected_prediction_records": 10,
        "prospective_status_at_definition": "outcomes_unobserved_predeclared_confirmation",
    },
)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include timezone: {value}")
    return parsed.astimezone(timezone.utc)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _verify_prediction(row: dict[str, Any]) -> None:
    unsigned = dict(row)
    stored = unsigned.pop("content_sha256", None)
    if stored != prediction_content_hash(unsigned):
        raise ValueError(f"Prediction {row.get('record_id')} failed content hash verification")


def _verify_settlement(row: dict[str, Any]) -> None:
    unsigned = dict(row)
    stored = unsigned.pop("content_sha256", None)
    if stored != settlement_content_hash(unsigned):
        raise ValueError(f"Settlement {row.get('settlement_id')} failed content hash verification")


def _select_batch_predictions(
    predictions: list[dict[str, Any]], batch: dict[str, Any]
) -> list[dict[str, Any]]:
    start = _parse_utc(str(batch["start_utc"]))
    end = _parse_utc(str(batch["end_exclusive_utc"]))
    selected: list[dict[str, Any]] = []
    for row in predictions:
        if str(row.get("snapshot_retrieved_at_utc")) != LOCKED_SNAPSHOT_UTC:
            continue
        kickoff = _parse_utc(str(row["commence_time_utc"]))
        if start <= kickoff < end:
            selected.append(row)
    selected.sort(key=lambda row: (str(row["commence_time_utc"]), str(row["event_id"])))
    expected = int(batch["expected_prediction_records"])
    if len(selected) != expected:
        raise ValueError(
            f"Frozen batch {batch['batch_id']} expected {expected} predictions but found {len(selected)}"
        )
    return selected


def _batch_settlements(
    settlements: list[dict[str, Any]], selected_prediction_ids: set[str]
) -> list[dict[str, Any]]:
    return [
        row
        for row in settlements
        if str(row["prediction_record_id"]) in selected_prediction_ids
    ]


def _by_result(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        label: _summary([row for row in rows if row["result"] == label])
        for label in ("home", "draw", "away")
    }


def _stage(predictions: int, settlements: int) -> str:
    if settlements == 0:
        return "prospective_frozen"
    if settlements < predictions:
        return "prospective_partial"
    if settlements == predictions:
        return "prospective_complete"
    raise ValueError("Settlements cannot exceed batch predictions")


def build_report(ledger_path: Path, settlement_path: Path) -> dict[str, Any]:
    predictions = _load_jsonl(ledger_path)
    settlements = _load_jsonl(settlement_path)
    for row in predictions:
        _verify_prediction(row)
    for row in settlements:
        _verify_settlement(row)

    prediction_by_id = {str(row["record_id"]): row for row in predictions}
    if len(prediction_by_id) != len(predictions):
        raise ValueError("Duplicate prediction record id")
    for settlement in settlements:
        prediction_id = str(settlement["prediction_record_id"])
        prediction = prediction_by_id.get(prediction_id)
        if prediction is None:
            raise ValueError(f"Settlement references unknown prediction {prediction_id}")
        if str(settlement["prediction_content_sha256"]) != str(prediction["content_sha256"]):
            raise ValueError(f"Settlement prediction hash mismatch for {prediction_id}")

    batch_reports: list[dict[str, Any]] = []
    for batch in BATCHES:
        selected = _select_batch_predictions(predictions, batch)
        selected_ids = {str(row["record_id"]) for row in selected}
        selected_settlements = _batch_settlements(settlements, selected_ids)
        paired = _pair_rows(selected, selected_settlements)
        batch_reports.append(
            {
                **batch,
                "locked_snapshot_utc": LOCKED_SNAPSHOT_UTC,
                "prediction_records": len(selected),
                "settled_records": len(selected_settlements),
                "unsettled_records": len(selected) - len(selected_settlements),
                "evidence_stage": _stage(len(selected), len(selected_settlements)),
                "prediction_record_ids": [str(row["record_id"]) for row in selected],
                "prediction_content_sha256": [str(row["content_sha256"]) for row in selected],
                "overall_when_settled": _summary(paired),
                "by_realized_result_when_settled": _by_result(paired),
            }
        )

    first = batch_reports[0]
    confirmation = batch_reports[1]
    comparison: dict[str, Any] = {
        "available": bool(first["settled_records"] and confirmation["settled_records"]),
        "complete_common_interpretation_allowed": (
            first["evidence_stage"] == "prospective_complete"
            and confirmation["evidence_stage"] == "prospective_complete"
        ),
        "predeclared_comparison_metrics": [
            "overall_help_fraction_all_matches",
            "overall_mean_realized_outcome_probability_delta_model_minus_market",
            "overall_mean_log_loss_delta_model_minus_market",
            "overall_mean_brier_delta_model_minus_market",
            "draw_model_helped_realized_outcome_count",
            "draw_model_hurt_realized_outcome_count",
            "draw_mean_realized_outcome_probability_delta_model_minus_market",
            "draw_mean_log_loss_delta_model_minus_market",
            "draw_mean_brier_delta_model_minus_market",
        ],
        "directional_question": (
            "Does the 12-14 September confirmation batch reproduce the first batch's tendency "
            "for Football 1 to move probability away from Draw on matches that actually draw?"
        ),
        "pass_fail_rule": None,
        "minimum_draw_count_rule": None,
    }

    if comparison["available"]:
        first_overall = first["overall_when_settled"]
        second_overall = confirmation["overall_when_settled"]
        first_draw = first["by_realized_result_when_settled"]["draw"]
        second_draw = confirmation["by_realized_result_when_settled"]["draw"]
        comparison["current_deltas_confirmation_minus_first"] = {
            "overall_help_fraction_all_matches": (
                None
                if first_overall["help_fraction_all_matches"] is None
                or second_overall["help_fraction_all_matches"] is None
                else float(second_overall["help_fraction_all_matches"])
                - float(first_overall["help_fraction_all_matches"])
            ),
            "overall_mean_realized_outcome_probability_delta_model_minus_market": (
                None
                if first_overall["mean_realized_outcome_probability_delta_model_minus_market"] is None
                or second_overall["mean_realized_outcome_probability_delta_model_minus_market"] is None
                else float(second_overall["mean_realized_outcome_probability_delta_model_minus_market"])
                - float(first_overall["mean_realized_outcome_probability_delta_model_minus_market"])
            ),
            "overall_mean_log_loss_delta_model_minus_market": (
                None
                if first_overall["mean_log_loss_delta_model_minus_market"] is None
                or second_overall["mean_log_loss_delta_model_minus_market"] is None
                else float(second_overall["mean_log_loss_delta_model_minus_market"])
                - float(first_overall["mean_log_loss_delta_model_minus_market"])
            ),
            "draw_helped_count": int(second_draw["model_helped_realized_outcome"])
            - int(first_draw["model_helped_realized_outcome"]),
            "draw_hurt_count": int(second_draw["model_hurt_realized_outcome"])
            - int(first_draw["model_hurt_realized_outcome"]),
            "draw_mean_realized_outcome_probability_delta_model_minus_market": (
                None
                if first_draw["mean_realized_outcome_probability_delta_model_minus_market"] is None
                or second_draw["mean_realized_outcome_probability_delta_model_minus_market"] is None
                else float(second_draw["mean_realized_outcome_probability_delta_model_minus_market"])
                - float(first_draw["mean_realized_outcome_probability_delta_model_minus_market"])
            ),
        }

    return {
        "experiment": "prospective_probability_error_two_batch_comparison_v1",
        "status": "predeclared_zero_decision_weight_batch_comparison",
        "decision_weight": 0.0,
        "model_change_allowed_from_report": False,
        "selection_rule": None,
        "locked_snapshot_utc": LOCKED_SNAPSHOT_UTC,
        "batches": batch_reports,
        "comparison": comparison,
        "guardrails": [
            "Batch membership is frozen by the original 4 September snapshot timestamp plus fixed kickoff windows.",
            "Later prediction snapshots for the same fixtures are excluded from this comparison.",
            "No minimum draw count, pass/fail threshold or promotion rule is defined.",
            "The first batch was already observed when this comparison was defined; only the 12-14 September batch is forward confirmation for the draw-error pattern.",
            "Do not alter Football 1 probabilities, residual weight or Draw Possibility from this report alone.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare two frozen Football 1 prospective error batches.")
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--settlements", type=Path, default=Path("prospective/settlements.jsonl"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(args.ledger, args.settlements)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote prospective error batch comparison to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
