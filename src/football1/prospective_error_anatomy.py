from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from football1.prospective import prediction_content_hash
from football1.settlement import settlement_content_hash


LABELS = ("home", "draw", "away")
EPSILON = 1e-12


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


def _probabilities(raw: dict[str, Any]) -> dict[str, float]:
    values = {label: float(raw[label]) for label in LABELS}
    if any((not math.isfinite(value)) or value <= 0.0 or value >= 1.0 for value in values.values()):
        raise ValueError("H/D/A probabilities must be finite and strictly between zero and one")
    if not math.isclose(sum(values.values()), 1.0, abs_tol=1e-7):
        raise ValueError("H/D/A probabilities must sum to one")
    return values


def _brier(probability: dict[str, float], result: str) -> float:
    return sum((probability[label] - (1.0 if label == result else 0.0)) ** 2 for label in LABELS)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _direction(delta: float) -> str:
    if delta > EPSILON:
        return "helped_realized_outcome"
    if delta < -EPSILON:
        return "hurt_realized_outcome"
    return "unchanged_realized_outcome"


def _pair_rows(
    predictions: list[dict[str, Any]],
    settlements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    for row in predictions:
        _verify_prediction(row)
    for row in settlements:
        _verify_settlement(row)

    by_id = {str(row["record_id"]): row for row in predictions}
    if len(by_id) != len(predictions):
        raise ValueError("Duplicate prediction record id")

    paired: list[dict[str, Any]] = []
    seen_settlement_prediction_ids: set[str] = set()
    for settlement in settlements:
        prediction_id = str(settlement["prediction_record_id"])
        if prediction_id in seen_settlement_prediction_ids:
            raise ValueError(f"Duplicate settlement for prediction {prediction_id}")
        prediction = by_id.get(prediction_id)
        if prediction is None:
            raise ValueError(f"Settlement references unknown prediction {prediction_id}")
        if str(settlement["prediction_content_sha256"]) != str(prediction["content_sha256"]):
            raise ValueError(f"Settlement prediction hash mismatch for {prediction_id}")

        result = str(settlement["result"])
        if result not in LABELS:
            raise ValueError(f"Invalid realized result {result}")
        market = _probabilities(prediction["market_anchor"]["probability"])
        model = _probabilities(prediction["model"]["probability"])
        movement = {label: model[label] - market[label] for label in LABELS}
        if not math.isclose(sum(movement.values()), 0.0, abs_tol=1e-9):
            raise ValueError("Model-minus-market probability movement must sum to zero")

        market_ll = -math.log(market[result])
        model_ll = -math.log(model[result])
        market_brier = _brier(market, result)
        model_brier = _brier(model, result)
        for key, calculated in (
            ("market_log_loss", market_ll),
            ("model_log_loss", model_ll),
            ("market_brier", market_brier),
            ("model_brier", model_brier),
        ):
            if key in settlement and not math.isclose(float(settlement[key]), calculated, abs_tol=1e-10):
                raise ValueError(f"Settlement {key} disagrees with locked probabilities for {prediction_id}")

        actual_delta = movement[result]
        max_move_label = max(LABELS, key=lambda label: abs(movement[label]))
        paired.append(
            {
                "prediction_record_id": prediction_id,
                "event_id": str(prediction["event_id"]),
                "commence_time_utc": str(prediction["commence_time_utc"]),
                "home": str(prediction["home_team_canonical"]),
                "away": str(prediction["away_team_canonical"]),
                "result": result,
                "market_probability_realized_outcome": market[result],
                "model_probability_realized_outcome": model[result],
                "realized_outcome_probability_delta_model_minus_market": actual_delta,
                "realized_outcome_direction": _direction(actual_delta),
                "probability_move_model_minus_market": movement,
                "l1_probability_shift_from_market": sum(abs(value) for value in movement.values()),
                "largest_absolute_probability_move_outcome": max_move_label,
                "largest_absolute_probability_move": movement[max_move_label],
                "market_log_loss": market_ll,
                "model_log_loss": model_ll,
                "log_loss_delta_model_minus_market": model_ll - market_ll,
                "market_brier": market_brier,
                "model_brier": model_brier,
                "brier_delta_model_minus_market": model_brier - market_brier,
            }
        )
        seen_settlement_prediction_ids.add(prediction_id)

    paired.sort(key=lambda row: (row["commence_time_utc"], row["event_id"]))
    return paired


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    helped = [row for row in rows if row["realized_outcome_direction"] == "helped_realized_outcome"]
    hurt = [row for row in rows if row["realized_outcome_direction"] == "hurt_realized_outcome"]
    unchanged = [row for row in rows if row["realized_outcome_direction"] == "unchanged_realized_outcome"]
    return {
        "matches": len(rows),
        "model_helped_realized_outcome": len(helped),
        "model_hurt_realized_outcome": len(hurt),
        "model_unchanged_realized_outcome": len(unchanged),
        "help_fraction_all_matches": len(helped) / len(rows) if rows else None,
        "mean_realized_outcome_probability_delta_model_minus_market": _mean(
            [float(row["realized_outcome_probability_delta_model_minus_market"]) for row in rows]
        ),
        "mean_l1_probability_shift_from_market": _mean(
            [float(row["l1_probability_shift_from_market"]) for row in rows]
        ),
        "mean_log_loss_delta_model_minus_market": _mean(
            [float(row["log_loss_delta_model_minus_market"]) for row in rows]
        ),
        "mean_brier_delta_model_minus_market": _mean(
            [float(row["brier_delta_model_minus_market"]) for row in rows]
        ),
    }


def build_report(prediction_path: Path, settlement_path: Path) -> dict[str, Any]:
    predictions = _load_jsonl(prediction_path)
    settlements = _load_jsonl(settlement_path)
    rows = _pair_rows(predictions, settlements)
    by_result = {
        label: _summary([row for row in rows if row["result"] == label])
        for label in LABELS
    }
    harm = sorted(rows, key=lambda row: float(row["log_loss_delta_model_minus_market"]), reverse=True)
    help_rows = sorted(rows, key=lambda row: float(row["log_loss_delta_model_minus_market"]))

    return {
        "experiment": "prospective_probability_error_anatomy_v1",
        "status": "descriptive_zero_decision_weight",
        "decision_weight": 0.0,
        "selection_rule": None,
        "model_change_allowed_from_report": False,
        "settled_matches": len(rows),
        "overall": _summary(rows),
        "by_realized_result": by_result,
        "largest_log_loss_harm_contributors": harm[: min(3, len(harm))],
        "largest_log_loss_help_contributors": help_rows[: min(3, len(help_rows))],
        "matches": rows,
        "interpretation": {
            "helped_realized_outcome": "Football 1 assigned more probability than the locked market to the outcome that occurred; this necessarily improves log loss for that match.",
            "hurt_realized_outcome": "Football 1 assigned less probability than the locked market to the outcome that occurred; this necessarily worsens log loss for that match.",
            "brier_note": "Brier also depends on probability assigned to the two unrealized outcomes, so its sign need not be inferred from the realized-outcome move alone.",
        },
        "guardrails": [
            "This report diagnoses immutable prospective predictions after settlement; it does not select matches or thresholds.",
            "Do not change residual weight, features or juror weights from a small settled batch.",
            "Largest contributors are descriptive attribution, not a feature-selection or exclusion rule.",
            "A model can lose this batch and later improve, or win this batch by luck; chronology and accumulation matter more than one matchweek.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decompose prospective Football 1 probability errors versus the locked market.")
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
        print(f"wrote prospective error anatomy report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
