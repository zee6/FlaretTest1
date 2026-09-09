from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from football1.prospective import prediction_content_hash
from football1.recency_shadow import content_hash as shadow_content_hash
from football1.settlement import settlement_content_hash


LABELS = ("home", "draw", "away")


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


def _verify_shadow(row: dict[str, Any]) -> None:
    unsigned = dict(row)
    stored = unsigned.pop("content_sha256", None)
    if stored != shadow_content_hash(unsigned):
        raise ValueError(f"Shadow {row.get('record_id')} failed content hash verification")
    if float(row.get("decision_weight", 1.0)) != 0.0:
        raise ValueError("Prospective recency shadow must have zero decision weight")


def _probability(raw: dict[str, Any], *, name: str) -> dict[str, float]:
    values = {label: float(raw[label]) for label in LABELS}
    if any(not math.isfinite(value) or value <= 0.0 or value >= 1.0 for value in values.values()):
        raise ValueError(f"{name} contains invalid probabilities")
    if not math.isclose(sum(values.values()), 1.0, abs_tol=1e-6):
        raise ValueError(f"{name} probabilities must sum to one")
    return values


def _same_probability(left: dict[str, Any], right: dict[str, Any], *, tolerance: float = 1e-12) -> bool:
    return all(math.isclose(float(left[label]), float(right[label]), abs_tol=tolerance) for label in LABELS)


def _log_loss(probability: dict[str, float], result: str) -> float:
    return -math.log(float(probability[result]))


def _brier(probability: dict[str, float], result: str) -> float:
    return sum((float(probability[label]) - (1.0 if label == result else 0.0)) ** 2 for label in LABELS)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _score(probability_by_event: dict[str, dict[str, float]], results: dict[str, str], common: list[str]) -> dict[str, Any]:
    if not common:
        return {
            "mean_log_loss": None,
            "mean_brier": None,
            "argmax_accuracy": None,
            "draw_probability_mean_all": None,
            "draw_probability_mean_realized_draws": None,
        }
    ll = [_log_loss(probability_by_event[event_id], results[event_id]) for event_id in common]
    brier = [_brier(probability_by_event[event_id], results[event_id]) for event_id in common]
    correct = sum(
        max(LABELS, key=lambda label: probability_by_event[event_id][label]) == results[event_id]
        for event_id in common
    )
    draw_all = [probability_by_event[event_id]["draw"] for event_id in common]
    realized_draws = [
        probability_by_event[event_id]["draw"]
        for event_id in common
        if results[event_id] == "draw"
    ]
    return {
        "mean_log_loss": _mean(ll),
        "mean_brier": _mean(brier),
        "argmax_accuracy": correct / len(common),
        "draw_probability_mean_all": _mean(draw_all),
        "draw_probability_mean_realized_draws": _mean(realized_draws),
    }


def build_report(
    prediction_path: Path,
    settlement_path: Path,
    shadow_paths: list[Path],
) -> dict[str, Any]:
    if not shadow_paths:
        raise ValueError("At least one recency shadow file is required")

    predictions = _load_jsonl(prediction_path)
    settlements = _load_jsonl(settlement_path)
    for row in predictions:
        _verify_prediction(row)
    for row in settlements:
        _verify_settlement(row)

    predictions_by_event: dict[str, dict[str, Any]] = {}
    predictions_by_id: dict[str, dict[str, Any]] = {}
    for row in predictions:
        event_id = str(row["event_id"])
        record_id = str(row["record_id"])
        if event_id in predictions_by_event or record_id in predictions_by_id:
            raise ValueError("Duplicate prediction event or record id")
        predictions_by_event[event_id] = row
        predictions_by_id[record_id] = row

    results: dict[str, str] = {}
    for row in settlements:
        event_id = str(row["event_id"])
        if event_id in results:
            raise ValueError(f"Duplicate settlement event: {event_id}")
        result = str(row["result"])
        if result not in LABELS:
            raise ValueError(f"Invalid settlement result: {result}")
        prediction = predictions_by_event.get(event_id)
        if prediction is None:
            raise ValueError(f"Settlement references unknown event: {event_id}")
        if row["prediction_record_id"] != prediction["record_id"]:
            raise ValueError(f"Settlement prediction id mismatch: {event_id}")
        if row["prediction_content_sha256"] != prediction["content_sha256"]:
            raise ValueError(f"Settlement prediction hash mismatch: {event_id}")
        results[event_id] = result

    shadow_models: dict[str, dict[str, dict[str, float]]] = {}
    shadow_event_sets: dict[str, set[str]] = {}
    shadow_metadata: list[dict[str, Any]] = []
    for path in shadow_paths:
        rows = _load_jsonl(path)
        if not rows:
            raise ValueError(f"Shadow file is empty: {path}")
        for row in rows:
            _verify_shadow(row)
        model_ids = {str(row["model_id"]) for row in rows}
        if len(model_ids) != 1:
            raise ValueError(f"Shadow file contains multiple model ids: {path}")
        model_id = next(iter(model_ids))
        if model_id in shadow_models:
            raise ValueError(f"Duplicate shadow model id: {model_id}")

        probability_by_event: dict[str, dict[str, float]] = {}
        for row in rows:
            event_id = str(row["event_id"])
            if event_id in probability_by_event:
                raise ValueError(f"Duplicate shadow event {event_id} in {path}")
            source = row["source_prediction"]
            source_id = str(source["record_id"])
            prediction = predictions_by_id.get(source_id)
            if prediction is None:
                raise ValueError(f"Shadow references unknown prediction {source_id}")
            if event_id != str(prediction["event_id"]):
                raise ValueError(f"Shadow event mismatch for prediction {source_id}")
            if str(source["content_sha256"]) != str(prediction["content_sha256"]):
                raise ValueError(f"Shadow source hash mismatch for {event_id}")
            if not _same_probability(row["market_probability"], prediction["market_anchor"]["probability"]):
                raise ValueError(f"Shadow market anchor mismatch for {event_id}")
            if not _same_probability(row["equal_weight_probability"], prediction["model"]["probability"]):
                raise ValueError(f"Shadow equal-weight probability mismatch for {event_id}")
            probability_by_event[event_id] = _probability(
                row["recency_probability"],
                name=f"{model_id}.{event_id}",
            )

        shadow_models[model_id] = probability_by_event
        shadow_event_sets[model_id] = set(probability_by_event)
        shadow_metadata.append(
            {
                "path": str(path),
                "model_id": model_id,
                "records": len(rows),
                "shadow_locked_at_utc_set": sorted({str(row["shadow_locked_at_utc"]) for row in rows}),
                "half_life_days_set": sorted({float(row["recency_policy"]["half_life_days"]) for row in rows}),
                "decision_weight_set": sorted({float(row["decision_weight"]) for row in rows}),
            }
        )

    common_shadow_events = set.intersection(*shadow_event_sets.values())
    if any(events != common_shadow_events for events in shadow_event_sets.values()):
        raise ValueError("Recency shadow files do not contain identical event sets")

    common = sorted(common_shadow_events & set(results))
    market = {
        event_id: _probability(predictions_by_event[event_id]["market_anchor"]["probability"], name=f"market.{event_id}")
        for event_id in common_shadow_events
    }
    equal = {
        event_id: _probability(predictions_by_event[event_id]["model"]["probability"], name=f"equal.{event_id}")
        for event_id in common_shadow_events
    }

    model_scores: dict[str, dict[str, Any]] = {
        "market_consensus": _score(market, results, common),
        "original_equal_weight_football1": _score(equal, results, common),
    }
    for model_id, probabilities in shadow_models.items():
        model_scores[model_id] = _score(probabilities, results, common)

    market_ll = model_scores["market_consensus"]["mean_log_loss"]
    market_brier = model_scores["market_consensus"]["mean_brier"]
    for key, score in model_scores.items():
        score["log_loss_delta_vs_market"] = (
            float(score["mean_log_loss"]) - float(market_ll)
            if score["mean_log_loss"] is not None and market_ll is not None
            else None
        )
        score["brier_delta_vs_market"] = (
            float(score["mean_brier"]) - float(market_brier)
            if score["mean_brier"] is not None and market_brier is not None
            else None
        )

    return {
        "status": "prospective_recency_comparison_zero_weight",
        "shadow_event_count": len(common_shadow_events),
        "settled_common_event_count": len(common),
        "unsettled_shadow_event_count": len(common_shadow_events) - len(common),
        "common_event_ids": common,
        "shadow_files": shadow_metadata,
        "models": model_scores,
        "guardrails": [
            "Lower log loss and Brier are better.",
            "All models are scored on exactly the same settled common event IDs.",
            "Recency shadow decision weight is zero.",
            "The 15-day candidate was chosen after inspected historical research and is post-hoc historically.",
            "Do not choose a half-life, threshold, stake rule or model weight from one 10-match prospective batch.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score prospective recency shadows on a strict common settled sample.")
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--settlements", type=Path, default=Path("prospective/settlements.jsonl"))
    parser.add_argument("--shadow", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(args.ledger, args.settlements, args.shadow)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote recency prospective report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
