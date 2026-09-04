from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from football1.prospective import prediction_content_hash
from football1.settlement import settlement_content_hash


THRESHOLDS = (0.025, 0.05, 0.075, 0.10)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _verify_predictions(rows: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for i, row in enumerate(rows, start=1):
        record_id = str(row.get("record_id", ""))
        if not record_id or record_id in seen:
            raise ValueError(f"Invalid or duplicate prediction record_id on line {i}")
        unsigned = dict(row)
        stored = unsigned.pop("content_sha256", None)
        if stored != prediction_content_hash(unsigned):
            raise ValueError(f"Prediction line {i} failed hash verification")
        seen.add(record_id)


def _verify_settlements(rows: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for i, row in enumerate(rows, start=1):
        prediction_id = str(row.get("prediction_record_id", ""))
        if not prediction_id or prediction_id in seen:
            raise ValueError(f"Invalid or duplicate settlement prediction id on line {i}")
        unsigned = dict(row)
        stored = unsigned.pop("content_sha256", None)
        if stored != settlement_content_hash(unsigned):
            raise ValueError(f"Settlement line {i} failed hash verification")
        seen.add(prediction_id)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _threshold_panel(
    predictions_by_id: dict[str, dict[str, Any]],
    settlements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for threshold in THRESHOLDS:
        selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for settlement in settlements:
            prediction = predictions_by_id[str(settlement["prediction_record_id"])]
            if float(prediction["model"]["max_predicted_ev"]) >= threshold:
                selected.append((prediction, settlement))

        pnl = sum(float(s["recorded_max_ev_selection_unit_pnl"]) for _, s in selected)
        rows.append(
            {
                "threshold": threshold,
                "settled_qualifying_records": len(selected),
                "mean_recorded_predicted_ev": _mean(
                    [float(p["model"]["max_predicted_ev"]) for p, _ in selected]
                ),
                "pnl_units": pnl,
                "roi": pnl / len(selected) if selected else None,
                "label": "sensitivity_only_not_strategy_selection",
            }
        )
    return rows


def build_report(prediction_path: Path, settlement_path: Path) -> dict[str, Any]:
    predictions = _load_jsonl(prediction_path)
    settlements = _load_jsonl(settlement_path)
    _verify_predictions(predictions)
    _verify_settlements(settlements)

    by_id = {str(row["record_id"]): row for row in predictions}
    for settlement in settlements:
        prediction_id = str(settlement["prediction_record_id"])
        prediction = by_id.get(prediction_id)
        if prediction is None:
            raise ValueError(f"Settlement references unknown prediction {prediction_id}")
        if settlement["prediction_content_sha256"] != prediction["content_sha256"]:
            raise ValueError(f"Settlement prediction hash mismatch for {prediction_id}")

    settled_ids = {str(row["prediction_record_id"]) for row in settlements}
    unsettled = [row for row in predictions if str(row["record_id"]) not in settled_ids]

    model_ll = [float(row["model_log_loss"]) for row in settlements]
    market_ll = [float(row["market_log_loss"]) for row in settlements]
    model_brier = [float(row["model_brier"]) for row in settlements]
    market_brier = [float(row["market_brier"]) for row in settlements]

    snapshots: dict[str, dict[str, int]] = defaultdict(lambda: {"predictions": 0, "settled": 0})
    for prediction in predictions:
        key = str(prediction["snapshot_retrieved_at_utc"])
        snapshots[key]["predictions"] += 1
        if str(prediction["record_id"]) in settled_ids:
            snapshots[key]["settled"] += 1

    return {
        "protocol": "prospective_v1",
        "prediction_records": len(predictions),
        "settled_records": len(settlements),
        "unsettled_records": len(unsettled),
        "unique_events": len({str(row["event_id"]) for row in predictions}),
        "snapshot_count": len(snapshots),
        "model_id_set": sorted({str(row["model"]["id"]) for row in predictions}),
        "probability_scoring": {
            "model_mean_log_loss": _mean(model_ll),
            "market_mean_log_loss": _mean(market_ll),
            "log_loss_delta_model_minus_market": (
                _mean(model_ll) - _mean(market_ll)
                if model_ll and market_ll
                else None
            ),
            "model_mean_brier": _mean(model_brier),
            "market_mean_brier": _mean(market_brier),
            "brier_delta_model_minus_market": (
                _mean(model_brier) - _mean(market_brier)
                if model_brier and market_brier
                else None
            ),
        },
        "threshold_sensitivity": _threshold_panel(by_id, settlements),
        "snapshots": [
            {
                "snapshot_retrieved_at_utc": key,
                **snapshots[key],
            }
            for key in sorted(snapshots)
        ],
        "interpretation_guardrails": [
            "Lower log loss and Brier are better.",
            "Threshold rows are a fixed sensitivity panel, not a strategy-selection mechanism.",
            "Do not promote a threshold because it has the best realized prospective ROI after observing results.",
            "The live market anchor is a multi-book UK consensus and is not historically equivalent to the B365 training anchor.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report Football 1 prospective validation results.")
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
        print(f"wrote prospective report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
