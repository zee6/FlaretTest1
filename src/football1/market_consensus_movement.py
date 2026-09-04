from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from football1.closing_movement_rf import _movement_error_summary, apply_predicted_movement
from football1.features import FEATURE_NAMES, FeatureRow, build_feature_rows, feature_vector
from football1.market_baseline import devig_decimal_odds
from football1.model_baseline import _mean_metrics, _top_label_ece


LABELS = ("home", "draw", "away")
OPEN_AVG_KEYS = ("AvgH", "AvgD", "AvgA")
CLOSE_AVG_KEYS = ("AvgCH", "AvgCD", "AvgCA")
OPEN_MAX_KEYS = ("MaxH", "MaxD", "MaxA")
MARKET_FEATURE_NAMES = ("opening_average_market_home", "opening_average_market_draw", "opening_average_market_away")
PREMIUM_FEATURE_NAMES = ("best_price_premium_home", "best_price_premium_draw", "best_price_premium_away")
BASE_FEATURE_NAMES = FEATURE_NAMES + MARKET_FEATURE_NAMES
AUGMENTED_FEATURE_NAMES = BASE_FEATURE_NAMES + PREMIUM_FEATURE_NAMES

DEFAULT_N_ESTIMATORS = 400
DEFAULT_MAX_DEPTH = 7
DEFAULT_MIN_SAMPLES_LEAF = 20
DEFAULT_MAX_FEATURES = "sqrt"
DEFAULT_RANDOM_STATE = 31
DEFAULT_MIN_TRAIN_SEASONS = 3


@dataclass(frozen=True)
class MarketConsensusObservation:
    base: FeatureRow
    opening_average_odds: tuple[float, float, float]
    closing_average_odds: tuple[float, float, float]
    opening_maximum_odds: tuple[float, float, float]

    @property
    def season_start_year(self) -> int:
        return self.base.season_start_year

    @property
    def result(self) -> str:
        return self.base.result


def _price(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 1.0:
        return None
    return number


def _triplet(raw: dict[str, Any], keys: tuple[str, str, str]) -> tuple[float, float, float] | None:
    values = tuple(_price(raw, key) for key in keys)
    if any(value is None for value in values):
        return None
    return (float(values[0]), float(values[1]), float(values[2]))


def consensus_odds_from_raw(
    raw: dict[str, Any],
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]] | None:
    opening = _triplet(raw, OPEN_AVG_KEYS)
    closing = _triplet(raw, CLOSE_AVG_KEYS)
    maximum = _triplet(raw, OPEN_MAX_KEYS)
    if opening is None or closing is None or maximum is None:
        return None
    return opening, closing, maximum


def best_price_premium(
    average_odds: tuple[float, float, float],
    maximum_odds: tuple[float, float, float],
) -> tuple[float, float, float]:
    values: list[float] = []
    for average, maximum in zip(average_odds, maximum_odds, strict=True):
        if average <= 1.0 or maximum <= 1.0:
            raise ValueError("decimal odds must be greater than 1")
        values.append(maximum / average - 1.0)
    return (values[0], values[1], values[2])


def build_market_consensus_observations(db_path: Path) -> list[MarketConsensusObservation]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT match_id, raw_json FROM matches ORDER BY match_date, match_id").fetchall()
    finally:
        conn.close()

    odds_by_match: dict[
        str,
        tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]],
    ] = {}
    for match_id, raw_json in rows:
        parsed = consensus_odds_from_raw(json.loads(raw_json))
        if parsed is not None:
            odds_by_match[str(match_id)] = parsed

    result: list[MarketConsensusObservation] = []
    for row in build_feature_rows(db_path):
        parsed = odds_by_match.get(row.match_id)
        if parsed is None:
            continue
        opening, closing, maximum = parsed
        result.append(
            MarketConsensusObservation(
                base=row,
                opening_average_odds=opening,
                closing_average_odds=closing,
                opening_maximum_odds=maximum,
            )
        )
    return result


def opening_probability(obs: MarketConsensusObservation) -> tuple[float, float, float]:
    return devig_decimal_odds(obs.opening_average_odds)[0]


def closing_probability(obs: MarketConsensusObservation) -> tuple[float, float, float]:
    return devig_decimal_odds(obs.closing_average_odds)[0]


def actual_movement(obs: MarketConsensusObservation) -> tuple[float, float, float]:
    opening = opening_probability(obs)
    closing = closing_probability(obs)
    return tuple(closing[i] - opening[i] for i in range(3))


def base_vector(obs: MarketConsensusObservation) -> list[float]:
    return feature_vector(obs.base) + list(opening_probability(obs))


def augmented_vector(obs: MarketConsensusObservation) -> list[float]:
    return base_vector(obs) + list(best_price_premium(obs.opening_average_odds, obs.opening_maximum_odds))


def _fit(train: list[MarketConsensusObservation], *, augmented: bool) -> RandomForestRegressor:
    model = RandomForestRegressor(
        n_estimators=DEFAULT_N_ESTIMATORS,
        max_depth=DEFAULT_MAX_DEPTH,
        min_samples_leaf=DEFAULT_MIN_SAMPLES_LEAF,
        max_features=DEFAULT_MAX_FEATURES,
        random_state=DEFAULT_RANDOM_STATE,
        n_jobs=-1,
    )
    vectors = [augmented_vector(obs) if augmented else base_vector(obs) for obs in train]
    model.fit(vectors, [actual_movement(obs) for obs in train])
    return model


def _predict(
    model: RandomForestRegressor,
    obs: MarketConsensusObservation,
    *,
    augmented: bool,
) -> tuple[float, float, float]:
    vector = augmented_vector(obs) if augmented else base_vector(obs)
    raw = np.asarray(model.predict([vector])[0], dtype=float)
    raw -= raw.mean()
    return (float(raw[0]), float(raw[1]), float(raw[2]))


def _probability_metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    result = _mean_metrics(items)
    result["top_label_ece"] = _top_label_ece(items)
    return result


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def _timing_summary(
    observations: list[MarketConsensusObservation],
    predicted_moves: list[tuple[float, float, float]],
) -> dict[str, Any]:
    if not observations:
        return {
            "matches": 0,
            "fraction_selected_outcome_actually_shortened": None,
            "mean_actual_probability_move_selected_outcome": None,
            "mean_first_vs_closing_average_price_ratio": None,
        }
    shortened = 0
    probability_moves: list[float] = []
    ratios: list[float] = []
    for obs, predicted in zip(observations, predicted_moves, strict=True):
        index = max(range(3), key=lambda i: predicted[i])
        movement = actual_movement(obs)[index]
        probability_moves.append(movement)
        if movement > 0.0:
            shortened += 1
        ratios.append(obs.opening_average_odds[index] / obs.closing_average_odds[index] - 1.0)
    n = len(observations)
    return {
        "matches": n,
        "selection_rule": "choose the H/D/A outcome with the largest predicted rise in de-vigged average-market probability; no movement-size threshold",
        "fraction_selected_outcome_actually_shortened": shortened / n,
        "mean_actual_probability_move_selected_outcome": sum(probability_moves) / n,
        "mean_first_vs_closing_average_price_ratio": sum(ratios) / n,
        "price_ratio_definition": "first_average_decimal_odds / closing_average_decimal_odds - 1; positive means the earlier average price was longer",
        "warning": "diagnostic only; not match-result P&L and not a betting rule",
    }


def _model_block(
    observations: list[MarketConsensusObservation],
    actual_moves: list[tuple[float, float, float]],
    predicted_moves: list[tuple[float, float, float]],
    opening_items: list[tuple[tuple[float, float, float], str]],
) -> dict[str, Any]:
    zero = [(0.0, 0.0, 0.0)] * len(observations)
    baseline_error = _movement_error_summary(actual_moves, zero)
    model_error = _movement_error_summary(actual_moves, predicted_moves)
    predicted_close_items = [
        (apply_predicted_movement(opening_probability(obs), move), obs.result)
        for obs, move in zip(observations, predicted_moves, strict=True)
    ]
    opening_metrics = _probability_metrics(opening_items)
    predicted_metrics = _probability_metrics(predicted_close_items)
    return {
        "movement_error": {
            **model_error,
            "mae_delta_vs_no_movement": _delta(
                model_error["mean_abs_error_per_outcome"], baseline_error["mean_abs_error_per_outcome"]
            ),
            "rmse_delta_vs_no_movement": _delta(model_error["rmse_per_outcome"], baseline_error["rmse_per_outcome"]),
        },
        "predicted_close_probability": {
            **predicted_metrics,
            "log_loss_delta_vs_first_market": _delta(predicted_metrics["log_loss"], opening_metrics["log_loss"]),
            "brier_delta_vs_first_market": _delta(predicted_metrics["brier"], opening_metrics["brier"]),
        },
        "price_timing": _timing_summary(observations, predicted_moves),
    }


def walk_forward_market_consensus_movement(
    db_path: Path,
    *,
    min_train_seasons: int = DEFAULT_MIN_TRAIN_SEASONS,
) -> dict[str, Any]:
    """Audit whether cross-book opening information helps forecast the later consensus move.

    Football-Data's Avg prices are an aggregate market price, not the same as a
    mean of individually de-vigged bookmaker probabilities. Max/Avg is used only
    as a best-price-premium proxy for cross-book disagreement, not as a true
    dispersion statistic.
    """
    observations = build_market_consensus_observations(db_path)
    seasons = sorted({obs.season_start_year for obs in observations})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons with complete average/max first and closing market odds")

    all_test: list[MarketConsensusObservation] = []
    all_actual: list[tuple[float, float, float]] = []
    all_base_moves: list[tuple[float, float, float]] = []
    all_augmented_moves: list[tuple[float, float, float]] = []
    all_opening_items: list[tuple[tuple[float, float, float], str]] = []
    all_closing_items: list[tuple[tuple[float, float, float], str]] = []
    season_reports: list[dict[str, Any]] = []
    latest_importance: dict[str, float] | None = None

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        training_seasons = seasons[:test_index]
        train = [obs for obs in observations if obs.season_start_year in training_seasons]
        test = [obs for obs in observations if obs.season_start_year == test_season]
        if not train or not test:
            continue

        base_model = _fit(train, augmented=False)
        augmented_model = _fit(train, augmented=True)
        actual = [actual_movement(obs) for obs in test]
        base_moves = [_predict(base_model, obs, augmented=False) for obs in test]
        augmented_moves = [_predict(augmented_model, obs, augmented=True) for obs in test]
        opening_items = [(opening_probability(obs), obs.result) for obs in test]
        closing_items = [(closing_probability(obs), obs.result) for obs in test]

        all_test.extend(test)
        all_actual.extend(actual)
        all_base_moves.extend(base_moves)
        all_augmented_moves.extend(augmented_moves)
        all_opening_items.extend(opening_items)
        all_closing_items.extend(closing_items)

        opening_metrics = _probability_metrics(opening_items)
        closing_metrics = _probability_metrics(closing_items)
        zero_error = _movement_error_summary(actual, [(0.0, 0.0, 0.0)] * len(test))
        season_reports.append(
            {
                "test_season_start_year": test_season,
                "training_seasons": training_seasons,
                "train_matches": len(train),
                "test_matches": len(test),
                "first_average_market": opening_metrics,
                "closing_average_market": {
                    **closing_metrics,
                    "log_loss_delta_vs_first": _delta(closing_metrics["log_loss"], opening_metrics["log_loss"]),
                    "brier_delta_vs_first": _delta(closing_metrics["brier"], opening_metrics["brier"]),
                },
                "no_movement_baseline": zero_error,
                "base_rf": _model_block(test, actual, base_moves, opening_items),
                "rf_plus_best_price_premium": _model_block(test, actual, augmented_moves, opening_items),
            }
        )

        if test_index == len(seasons) - 1:
            latest_importance = {
                name: float(value)
                for name, value in sorted(
                    zip(AUGMENTED_FEATURE_NAMES, augmented_model.feature_importances_, strict=True),
                    key=lambda item: item[1],
                    reverse=True,
                )
            }

    opening_metrics = _probability_metrics(all_opening_items)
    closing_metrics = _probability_metrics(all_closing_items)
    zero_error = _movement_error_summary(all_actual, [(0.0, 0.0, 0.0)] * len(all_test))
    base_block = _model_block(all_test, all_actual, all_base_moves, all_opening_items)
    augmented_block = _model_block(all_test, all_actual, all_augmented_moves, all_opening_items)

    return {
        "observer": "historical_average_market_closing_movement_rf_v1",
        "status": "historical_walk_forward_consensus_movement_audition_zero_live_weight",
        "market_definition": (
            "Football-Data AvgH/AvgD/AvgA first/pre-closing average market odds versus AvgCH/AvgCD/AvgCA closing average market odds. "
            "MaxH/MaxD/MaxA enters only as Max/Avg-1 best-price-premium proxy."
        ),
        "proxy_warning": "Max/Avg-1 is not true bookmaker probability dispersion; it is a historical cross-sectional best-price-premium proxy.",
        "split_policy": "walk-forward by seasons with complete first/closing average and first maximum odds; each test season uses only earlier eligible seasons",
        "hyperparameter_policy": (
            "Both forests use n_estimators=400, max_depth=7, min_samples_leaf=20, max_features=sqrt, random_state=31, "
            "min_train_seasons=3 fixed before inspection; no OOS tuning."
        ),
        "promotion_rule": (
            "No promotion from this retrospective audit. Any benefit from cross-book price premium must be frozen and survive fresh prospective testing with actual bookmaker-level snapshots."
        ),
        "base_feature_names": list(BASE_FEATURE_NAMES),
        "augmented_feature_names": list(AUGMENTED_FEATURE_NAMES),
        "eligible_matches": len(observations),
        "matches": len(all_test),
        "test_seasons": [report["test_season_start_year"] for report in season_reports],
        "overall": {
            "first_average_market": opening_metrics,
            "closing_average_market": {
                **closing_metrics,
                "log_loss_delta_vs_first": _delta(closing_metrics["log_loss"], opening_metrics["log_loss"]),
                "brier_delta_vs_first": _delta(closing_metrics["brier"], opening_metrics["brier"]),
            },
            "no_movement_baseline": zero_error,
            "base_rf": base_block,
            "rf_plus_best_price_premium": {
                **augmented_block,
                "mae_delta_vs_base_rf": _delta(
                    augmented_block["movement_error"]["mean_abs_error_per_outcome"],
                    base_block["movement_error"]["mean_abs_error_per_outcome"],
                ),
                "rmse_delta_vs_base_rf": _delta(
                    augmented_block["movement_error"]["rmse_per_outcome"],
                    base_block["movement_error"]["rmse_per_outcome"],
                ),
            },
        },
        "latest_augmented_training_impurity_importance": {
            "warning": "descriptive training-set impurity importance only; not OOS proof of feature value",
            "values": latest_importance,
        },
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit historical average-market closing movement and cross-book price-premium information.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=DEFAULT_MIN_TRAIN_SEASONS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_market_consensus_movement(args.database, min_train_seasons=args.min_train_seasons)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote market-consensus movement audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
