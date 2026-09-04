from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from football1.closing_movement_rf import _movement_error_summary
from football1.market_consensus_movement import (
    DEFAULT_MIN_TRAIN_SEASONS,
    _fit,
    _predict,
    actual_movement,
    build_market_consensus_observations,
)


def mean_movement(rows: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    if not rows:
        raise ValueError("rows must not be empty")
    n = len(rows)
    values = tuple(sum(row[i] for row in rows) / n for i in range(3))
    # Each source movement is on the probability simplex and sums to zero.
    # Remove floating-point residue so the baseline remains exactly zero-sum.
    correction = sum(values) / 3.0
    return (
        values[0] - correction,
        values[1] - correction,
        values[2] - correction,
    )


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def walk_forward_baseline_check(
    db_path: Path,
    *,
    min_train_seasons: int = DEFAULT_MIN_TRAIN_SEASONS,
) -> dict[str, Any]:
    """Check RF movement forecasts against both zero and a training-mean baseline.

    The mean movement for each test season is estimated only from earlier
    eligible seasons. This detects the case where an apparent RF advantage is
    merely a persistent unconditional opening-to-closing drift.
    """
    observations = build_market_consensus_observations(db_path)
    seasons = sorted({obs.season_start_year for obs in observations})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough eligible seasons")

    all_actual: list[tuple[float, float, float]] = []
    all_zero: list[tuple[float, float, float]] = []
    all_mean: list[tuple[float, float, float]] = []
    all_base: list[tuple[float, float, float]] = []
    all_augmented: list[tuple[float, float, float]] = []
    season_reports: list[dict[str, Any]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        training_seasons = seasons[:test_index]
        train = [obs for obs in observations if obs.season_start_year in training_seasons]
        test = [obs for obs in observations if obs.season_start_year == test_season]
        if not train or not test:
            continue

        train_mean = mean_movement([actual_movement(obs) for obs in train])
        actual = [actual_movement(obs) for obs in test]
        zero = [(0.0, 0.0, 0.0)] * len(test)
        mean_predictions = [train_mean] * len(test)
        base_model = _fit(train, augmented=False)
        augmented_model = _fit(train, augmented=True)
        base_predictions = [_predict(base_model, obs, augmented=False) for obs in test]
        augmented_predictions = [_predict(augmented_model, obs, augmented=True) for obs in test]

        zero_error = _movement_error_summary(actual, zero)
        mean_error = _movement_error_summary(actual, mean_predictions)
        base_error = _movement_error_summary(actual, base_predictions)
        augmented_error = _movement_error_summary(actual, augmented_predictions)

        season_reports.append(
            {
                "test_season_start_year": test_season,
                "training_seasons": training_seasons,
                "train_matches": len(train),
                "test_matches": len(test),
                "train_mean_movement": {
                    "home": train_mean[0], "draw": train_mean[1], "away": train_mean[2]
                },
                "zero_movement": zero_error,
                "training_mean_movement": mean_error,
                "base_rf": {
                    **base_error,
                    "mae_delta_vs_training_mean": _delta(base_error["mean_abs_error_per_outcome"], mean_error["mean_abs_error_per_outcome"]),
                    "rmse_delta_vs_training_mean": _delta(base_error["rmse_per_outcome"], mean_error["rmse_per_outcome"]),
                },
                "rf_plus_best_price_premium": {
                    **augmented_error,
                    "mae_delta_vs_training_mean": _delta(augmented_error["mean_abs_error_per_outcome"], mean_error["mean_abs_error_per_outcome"]),
                    "rmse_delta_vs_training_mean": _delta(augmented_error["rmse_per_outcome"], mean_error["rmse_per_outcome"]),
                    "mae_delta_vs_base_rf": _delta(augmented_error["mean_abs_error_per_outcome"], base_error["mean_abs_error_per_outcome"]),
                    "rmse_delta_vs_base_rf": _delta(augmented_error["rmse_per_outcome"], base_error["rmse_per_outcome"]),
                },
            }
        )

        all_actual.extend(actual)
        all_zero.extend(zero)
        all_mean.extend(mean_predictions)
        all_base.extend(base_predictions)
        all_augmented.extend(augmented_predictions)

    zero_error = _movement_error_summary(all_actual, all_zero)
    mean_error = _movement_error_summary(all_actual, all_mean)
    base_error = _movement_error_summary(all_actual, all_base)
    augmented_error = _movement_error_summary(all_actual, all_augmented)

    return {
        "observer": "average_market_movement_walk_forward_baseline_check_v1",
        "status": "historical_methodological_control_zero_live_weight",
        "purpose": "Distinguish individual-match predictive signal from an unconditional opening-to-closing drift learned on earlier seasons.",
        "split_policy": "Each training-mean and RF forecast for a test season uses only earlier eligible seasons.",
        "matches": len(all_actual),
        "test_seasons": [row["test_season_start_year"] for row in season_reports],
        "overall": {
            "zero_movement": zero_error,
            "training_mean_movement": mean_error,
            "base_rf": {
                **base_error,
                "mae_delta_vs_training_mean": _delta(base_error["mean_abs_error_per_outcome"], mean_error["mean_abs_error_per_outcome"]),
                "rmse_delta_vs_training_mean": _delta(base_error["rmse_per_outcome"], mean_error["rmse_per_outcome"]),
            },
            "rf_plus_best_price_premium": {
                **augmented_error,
                "mae_delta_vs_training_mean": _delta(augmented_error["mean_abs_error_per_outcome"], mean_error["mean_abs_error_per_outcome"]),
                "rmse_delta_vs_training_mean": _delta(augmented_error["rmse_per_outcome"], mean_error["rmse_per_outcome"]),
                "mae_delta_vs_base_rf": _delta(augmented_error["mean_abs_error_per_outcome"], base_error["mean_abs_error_per_outcome"]),
                "rmse_delta_vs_base_rf": _delta(augmented_error["rmse_per_outcome"], base_error["rmse_per_outcome"]),
            },
        },
        "promotion_rule": "No promotion. This is a control experiment; any surviving advantage still requires fresh prospective bookmaker-level testing.",
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check consensus-movement RF against a walk-forward historical mean-movement baseline.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=DEFAULT_MIN_TRAIN_SEASONS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_baseline_check(args.database, min_train_seasons=args.min_train_seasons)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote market-consensus baseline check to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
