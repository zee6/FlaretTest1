from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from football1.features import FEATURE_NAMES, FeatureRow, feature_vector
from football1.historical_closing_line import ClosingObservation, build_closing_observations
from football1.market_baseline import devig_decimal_odds
from football1.model_baseline import _mean_metrics, _top_label_ece
from football1.offset_slant import _market_probs


LABELS = ("home", "draw", "away")
MARKET_FEATURE_NAMES = ("opening_market_home", "opening_market_draw", "opening_market_away")
RF_FEATURE_NAMES = FEATURE_NAMES + MARKET_FEATURE_NAMES

# Frozen before this first audit. Deliberately mirrors the conservative tree
# complexity used by Football 1's earlier Random Forest outcome audition.
DEFAULT_N_ESTIMATORS = 400
DEFAULT_MAX_DEPTH = 7
DEFAULT_MIN_SAMPLES_LEAF = 20
DEFAULT_MAX_FEATURES = "sqrt"
DEFAULT_RANDOM_STATE = 23
DEFAULT_MIN_TRAIN_CLOSING_SEASONS = 3


def movement_feature_vector(row: FeatureRow) -> list[float]:
    """Leakage-safe football state plus the de-vigged opening market."""
    return feature_vector(row) + list(_market_probs(row))


def closing_probability(observation: ClosingObservation) -> tuple[float, float, float]:
    return devig_decimal_odds(observation.closing_odds)[0]


def actual_movement(observation: ClosingObservation) -> tuple[float, float, float]:
    opening = _market_probs(observation.base)
    closing = closing_probability(observation)
    return tuple(closing[i] - opening[i] for i in range(3))


def apply_predicted_movement(
    opening: tuple[float, float, float],
    predicted_movement: tuple[float, float, float] | list[float] | np.ndarray,
) -> tuple[float, float, float]:
    """Convert a predicted probability residual into a valid H/D/A distribution.

    This is a numerical projection only, not a live probability model. Tiny
    positive clipping prevents impossible negative probabilities if a tree
    ensemble extrapolates a residual beyond the simplex edge.
    """
    base = np.asarray(opening, dtype=float)
    move = np.asarray(predicted_movement, dtype=float)
    if base.shape != (3,) or move.shape != (3,):
        raise ValueError("opening and predicted_movement must each have three values")
    if np.any(~np.isfinite(base)) or np.any(~np.isfinite(move)) or np.any(base <= 0):
        raise ValueError("opening must be positive and all inputs finite")
    if not math.isclose(float(base.sum()), 1.0, abs_tol=1e-9):
        raise ValueError("opening must sum to 1")
    candidate = np.clip(base + move, 1e-9, None)
    candidate /= candidate.sum()
    return (float(candidate[0]), float(candidate[1]), float(candidate[2]))


def _fit(train: list[ClosingObservation]) -> RandomForestRegressor:
    model = RandomForestRegressor(
        n_estimators=DEFAULT_N_ESTIMATORS,
        max_depth=DEFAULT_MAX_DEPTH,
        min_samples_leaf=DEFAULT_MIN_SAMPLES_LEAF,
        max_features=DEFAULT_MAX_FEATURES,
        random_state=DEFAULT_RANDOM_STATE,
        n_jobs=-1,
    )
    x = [movement_feature_vector(obs.base) for obs in train]
    y = [actual_movement(obs) for obs in train]
    model.fit(x, y)
    return model


def _predict_movement(
    model: RandomForestRegressor,
    observation: ClosingObservation,
) -> tuple[float, float, float]:
    raw = model.predict([movement_feature_vector(observation.base)])[0]
    # A valid movement vector must sum to zero. Tree averages should already be
    # extremely close; subtracting the mean makes the constraint explicit.
    raw = np.asarray(raw, dtype=float)
    raw -= raw.mean()
    return (float(raw[0]), float(raw[1]), float(raw[2]))


def _probability_metrics(
    items: list[tuple[tuple[float, float, float], str]],
) -> dict[str, float | int | None]:
    result = _mean_metrics(items)
    result["top_label_ece"] = _top_label_ece(items)
    return result


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def _movement_error_summary(
    actual: list[tuple[float, float, float]],
    predicted: list[tuple[float, float, float]],
) -> dict[str, float | int | None]:
    if not actual:
        return {
            "matches": 0,
            "mean_abs_error_per_outcome": None,
            "rmse_per_outcome": None,
            "mean_match_l1_error": None,
            "direction_evaluated_outcomes": 0,
            "direction_accuracy_nonzero_predictions": None,
        }

    errors: list[float] = []
    squared: list[float] = []
    l1_by_match: list[float] = []
    direction_hits = 0
    direction_n = 0
    for actual_move, predicted_move in zip(actual, predicted, strict=True):
        match_errors = []
        for index in range(3):
            error = predicted_move[index] - actual_move[index]
            errors.append(abs(error))
            squared.append(error * error)
            match_errors.append(abs(error))
            # A literal zero forecast has no direction. This makes the hard
            # no-movement baseline report direction_accuracy=None rather than
            # accidentally treating every negative realized move as a hit.
            if actual_move[index] != 0.0 and predicted_move[index] != 0.0:
                direction_n += 1
                if (predicted_move[index] > 0) == (actual_move[index] > 0):
                    direction_hits += 1
        l1_by_match.append(sum(match_errors))

    return {
        "matches": len(actual),
        "mean_abs_error_per_outcome": sum(errors) / len(errors),
        "rmse_per_outcome": math.sqrt(sum(squared) / len(squared)),
        "mean_match_l1_error": sum(l1_by_match) / len(l1_by_match),
        "direction_evaluated_outcomes": direction_n,
        "direction_accuracy_nonzero_predictions": direction_hits / direction_n if direction_n else None,
    }


def _price_timing_summary(
    observations: list[ClosingObservation],
    predicted_moves: list[tuple[float, float, float]],
) -> dict[str, float | int | None | str]:
    if not observations:
        return {
            "matches": 0,
            "fraction_selected_outcome_actually_shortened": None,
            "mean_actual_probability_move_selected_outcome": None,
            "mean_opening_vs_closing_decimal_price_ratio": None,
        }

    shortened = 0
    actual_moves: list[float] = []
    price_ratios: list[float] = []
    for obs, predicted in zip(observations, predicted_moves, strict=True):
        selected = max(range(3), key=lambda i: predicted[i])
        actual = actual_movement(obs)[selected]
        actual_moves.append(actual)
        if actual > 0.0:
            shortened += 1
        opening_odds = (
            float(obs.base.b365_home),
            float(obs.base.b365_draw),
            float(obs.base.b365_away),
        )
        closing_odds = obs.closing_odds
        price_ratios.append(opening_odds[selected] / closing_odds[selected] - 1.0)

    return {
        "matches": len(observations),
        "selection_rule": "choose the H/D/A outcome with the largest RF-predicted increase in de-vigged probability; no movement-size threshold",
        "fraction_selected_outcome_actually_shortened": shortened / len(observations),
        "mean_actual_probability_move_selected_outcome": sum(actual_moves) / len(actual_moves),
        "mean_opening_vs_closing_decimal_price_ratio": sum(price_ratios) / len(price_ratios),
        "price_ratio_definition": "opening_decimal_odds / closing_decimal_odds - 1; positive means the opening quote was longer than the close",
        "warning": "price-timing diagnostic only; not match-result P&L and not a betting rule",
    }


def walk_forward_closing_movement_rf(
    db_path: Path,
    *,
    min_train_closing_seasons: int = DEFAULT_MIN_TRAIN_CLOSING_SEASONS,
) -> dict[str, Any]:
    """Ask whether pre-match information predicts the later Bet365 closing move.

    The target is closing minus opening de-vigged probability. Each test season
    is predicted by a Random Forest trained only on earlier seasons for which
    complete B365 closing triplets exist. Match results are not the training
    target. Closing prices never appear in the feature vector.
    """
    observations = build_closing_observations(db_path)
    seasons = sorted({obs.season_start_year for obs in observations})
    if len(seasons) <= min_train_closing_seasons:
        raise ValueError("Not enough seasons with closing prices for walk-forward evaluation")

    all_opening_items: list[tuple[tuple[float, float, float], str]] = []
    all_closing_items: list[tuple[tuple[float, float, float], str]] = []
    all_predicted_close_items: list[tuple[tuple[float, float, float], str]] = []
    all_actual_moves: list[tuple[float, float, float]] = []
    all_zero_moves: list[tuple[float, float, float]] = []
    all_predicted_moves: list[tuple[float, float, float]] = []
    all_test_observations: list[ClosingObservation] = []
    season_reports: list[dict[str, Any]] = []
    latest_importance: dict[str, float] | None = None

    for test_index in range(min_train_closing_seasons, len(seasons)):
        test_season = seasons[test_index]
        training_seasons = seasons[:test_index]
        train = [obs for obs in observations if obs.season_start_year in training_seasons]
        test = [obs for obs in observations if obs.season_start_year == test_season]
        if not train or not test:
            continue
        model = _fit(train)

        opening_items: list[tuple[tuple[float, float, float], str]] = []
        closing_items: list[tuple[tuple[float, float, float], str]] = []
        predicted_close_items: list[tuple[tuple[float, float, float], str]] = []
        actual_moves: list[tuple[float, float, float]] = []
        zero_moves: list[tuple[float, float, float]] = []
        predicted_moves: list[tuple[float, float, float]] = []

        for obs in test:
            opening = _market_probs(obs.base)
            closing = closing_probability(obs)
            predicted_move = _predict_movement(model, obs)
            predicted_close = apply_predicted_movement(opening, predicted_move)
            actual_move = tuple(closing[i] - opening[i] for i in range(3))

            opening_items.append((opening, obs.result))
            closing_items.append((closing, obs.result))
            predicted_close_items.append((predicted_close, obs.result))
            actual_moves.append(actual_move)
            zero_moves.append((0.0, 0.0, 0.0))
            predicted_moves.append(predicted_move)

        all_opening_items.extend(opening_items)
        all_closing_items.extend(closing_items)
        all_predicted_close_items.extend(predicted_close_items)
        all_actual_moves.extend(actual_moves)
        all_zero_moves.extend(zero_moves)
        all_predicted_moves.extend(predicted_moves)
        all_test_observations.extend(test)

        opening_metrics = _probability_metrics(opening_items)
        closing_metrics = _probability_metrics(closing_items)
        predicted_metrics = _probability_metrics(predicted_close_items)
        baseline_error = _movement_error_summary(actual_moves, zero_moves)
        rf_error = _movement_error_summary(actual_moves, predicted_moves)

        season_reports.append(
            {
                "test_season_start_year": test_season,
                "training_seasons": training_seasons,
                "train_matches": len(train),
                "test_matches": len(test),
                "opening_market": opening_metrics,
                "actual_closing_market": {
                    **closing_metrics,
                    "log_loss_delta_vs_opening": _delta(closing_metrics["log_loss"], opening_metrics["log_loss"]),
                    "brier_delta_vs_opening": _delta(closing_metrics["brier"], opening_metrics["brier"]),
                },
                "rf_predicted_close": {
                    **predicted_metrics,
                    "log_loss_delta_vs_opening": _delta(predicted_metrics["log_loss"], opening_metrics["log_loss"]),
                    "brier_delta_vs_opening": _delta(predicted_metrics["brier"], opening_metrics["brier"]),
                },
                "closing_movement_forecast": {
                    "no_movement_baseline": baseline_error,
                    "random_forest": {
                        **rf_error,
                        "mae_delta_vs_no_movement": _delta(
                            rf_error["mean_abs_error_per_outcome"],
                            baseline_error["mean_abs_error_per_outcome"],
                        ),
                        "rmse_delta_vs_no_movement": _delta(
                            rf_error["rmse_per_outcome"], baseline_error["rmse_per_outcome"]
                        ),
                    },
                    "price_timing": _price_timing_summary(test, predicted_moves),
                },
            }
        )

        if test_index == len(seasons) - 1:
            latest_importance = {
                name: float(value)
                for name, value in sorted(
                    zip(RF_FEATURE_NAMES, model.feature_importances_, strict=True),
                    key=lambda item: item[1],
                    reverse=True,
                )
            }

    opening_metrics = _probability_metrics(all_opening_items)
    closing_metrics = _probability_metrics(all_closing_items)
    predicted_metrics = _probability_metrics(all_predicted_close_items)
    baseline_error = _movement_error_summary(all_actual_moves, all_zero_moves)
    rf_error = _movement_error_summary(all_actual_moves, all_predicted_moves)

    return {
        "observer": "random_forest_b365_closing_movement_v1",
        "status": "historical_walk_forward_market_movement_audition_zero_live_weight",
        "target": "de-vigged B365 closing probability minus de-vigged B365 first/pre-closing probability",
        "feature_names": list(RF_FEATURE_NAMES),
        "split_policy": "walk-forward by closing-price season; each test season uses only earlier closing-price seasons for training",
        "same_day_policy": "football features are date-frozen before same-date match results update state",
        "leakage_guard": "B365 closing prices are training targets only for earlier seasons and never appear in test features",
        "hyperparameter_policy": (
            "n_estimators=400, max_depth=7, min_samples_leaf=20, max_features=sqrt, random_state=23, "
            "min_train_closing_seasons=3 frozen before first OOS audit; no OOS tuning"
        ),
        "promotion_rule": (
            "No promotion from this audit. Any apparent ability to forecast closing movement must survive a frozen fresh/prospective test. "
            "No movement threshold or subgroup may be selected after inspecting these results."
        ),
        "matches": len(all_test_observations),
        "test_seasons": [report["test_season_start_year"] for report in season_reports],
        "overall": {
            "opening_market": opening_metrics,
            "actual_closing_market": {
                **closing_metrics,
                "log_loss_delta_vs_opening": _delta(closing_metrics["log_loss"], opening_metrics["log_loss"]),
                "brier_delta_vs_opening": _delta(closing_metrics["brier"], opening_metrics["brier"]),
            },
            "rf_predicted_close": {
                **predicted_metrics,
                "log_loss_delta_vs_opening": _delta(predicted_metrics["log_loss"], opening_metrics["log_loss"]),
                "brier_delta_vs_opening": _delta(predicted_metrics["brier"], opening_metrics["brier"]),
            },
            "closing_movement_forecast": {
                "no_movement_baseline": baseline_error,
                "random_forest": {
                    **rf_error,
                    "mae_delta_vs_no_movement": _delta(
                        rf_error["mean_abs_error_per_outcome"],
                        baseline_error["mean_abs_error_per_outcome"],
                    ),
                    "rmse_delta_vs_no_movement": _delta(
                        rf_error["rmse_per_outcome"], baseline_error["rmse_per_outcome"]
                    ),
                },
                "price_timing": _price_timing_summary(all_test_observations, all_predicted_moves),
            },
        },
        "latest_training_impurity_importance": {
            "warning": "descriptive training-set Random Forest impurity importance only; not OOS proof that a feature causes or adds value",
            "values": latest_importance,
        },
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Random Forest forecasts of Bet365 closing-line movement.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-closing-seasons", type=int, default=DEFAULT_MIN_TRAIN_CLOSING_SEASONS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_closing_movement_rf(
        args.database,
        min_train_closing_seasons=args.min_train_closing_seasons,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote Random Forest closing-movement audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
