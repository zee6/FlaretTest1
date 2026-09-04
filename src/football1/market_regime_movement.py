from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from football1.closing_movement_rf import (
    DEFAULT_MIN_TRAIN_CLOSING_SEASONS,
    _fit,
    _movement_error_summary,
    _predict_movement,
    _price_timing_summary,
    actual_movement,
    closing_probability,
)
from football1.historical_closing_line import ClosingObservation, build_closing_observations
from football1.market_regime_audit import (
    REGIME_DEFINITIONS,
    REGIME_ORDER,
    favorite_price_regime,
    favorite_selection,
)
from football1.model_baseline import _mean_metrics, _top_label_ece
from football1.offset_slant import _market_probs


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


def opening_favorite_closing_summary(observations: list[ClosingObservation]) -> dict[str, float | int | None | str]:
    if not observations:
        return {
            "matches": 0,
            "fraction_opening_favorite_shortened": None,
            "mean_opening_favorite_probability_move": None,
            "mean_opening_vs_closing_decimal_price_ratio": None,
        }

    shortened = 0
    probability_moves: list[float] = []
    price_ratios: list[float] = []
    for obs in observations:
        index, opening_price, _ = favorite_selection(obs.base)
        opening_probability = _market_probs(obs.base)[index]
        closing_prob = closing_probability(obs)[index]
        probability_moves.append(closing_prob - opening_probability)
        closing_price = float(obs.closing_odds[index])
        price_ratios.append(opening_price / closing_price - 1.0)
        if closing_price < opening_price:
            shortened += 1

    n = len(observations)
    return {
        "matches": n,
        "fraction_opening_favorite_shortened": shortened / n,
        "mean_opening_favorite_probability_move": sum(probability_moves) / n,
        "mean_opening_vs_closing_decimal_price_ratio": sum(price_ratios) / n,
        "price_ratio_definition": "opening_decimal_odds / closing_decimal_odds - 1; positive means the opening favorite was longer at the opening snapshot",
    }


def _bucket_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "matches": 0,
            "opening_market": _probability_metrics([]),
            "actual_closing_market": _probability_metrics([]),
            "closing_movement_forecast": {
                "no_movement_baseline": _movement_error_summary([], []),
                "random_forest": _movement_error_summary([], []),
                "price_timing": _price_timing_summary([], []),
            },
            "opening_favorite_to_close": opening_favorite_closing_summary([]),
        }

    observations = [r["observation"] for r in records]
    actual = [r["actual_move"] for r in records]
    predicted = [r["predicted_move"] for r in records]
    zero = [(0.0, 0.0, 0.0)] * len(records)
    opening_items = [(r["opening"], r["observation"].result) for r in records]
    closing_items = [(r["closing"], r["observation"].result) for r in records]

    opening_metrics = _probability_metrics(opening_items)
    closing_metrics = _probability_metrics(closing_items)
    baseline = _movement_error_summary(actual, zero)
    rf = _movement_error_summary(actual, predicted)

    return {
        "matches": len(records),
        "opening_market": opening_metrics,
        "actual_closing_market": {
            **closing_metrics,
            "log_loss_delta_vs_opening": _delta(closing_metrics["log_loss"], opening_metrics["log_loss"]),
            "brier_delta_vs_opening": _delta(closing_metrics["brier"], opening_metrics["brier"]),
        },
        "closing_movement_forecast": {
            "no_movement_baseline": baseline,
            "random_forest": {
                **rf,
                "mae_delta_vs_no_movement": _delta(
                    rf["mean_abs_error_per_outcome"], baseline["mean_abs_error_per_outcome"]
                ),
                "rmse_delta_vs_no_movement": _delta(rf["rmse_per_outcome"], baseline["rmse_per_outcome"]),
            },
            "price_timing": _price_timing_summary(observations, predicted),
        },
        "opening_favorite_to_close": opening_favorite_closing_summary(observations),
    }


def walk_forward_market_regime_movement_audit(
    db_path: Path,
    *,
    min_train_closing_seasons: int = DEFAULT_MIN_TRAIN_CLOSING_SEASONS,
) -> dict[str, Any]:
    """Segment the frozen RF closing-movement audition by pre-declared price regime.

    This is a retrospective subgroup observer. The regime thresholds were
    fixed before this segmentation and are not changed after results. Even a
    strong-looking bucket cannot be promoted without a fresh prospective test.
    """
    observations = build_closing_observations(db_path)
    seasons = sorted({obs.season_start_year for obs in observations})
    if len(seasons) <= min_train_closing_seasons:
        raise ValueError("Not enough seasons with closing prices for walk-forward evaluation")

    overall_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    season_reports: list[dict[str, Any]] = []

    for test_index in range(min_train_closing_seasons, len(seasons)):
        test_season = seasons[test_index]
        training_seasons = seasons[:test_index]
        train = [obs for obs in observations if obs.season_start_year in training_seasons]
        test = [obs for obs in observations if obs.season_start_year == test_season]
        if not train or not test:
            continue

        model = _fit(train)
        season_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for obs in test:
            _, favorite_odds, _ = favorite_selection(obs.base)
            regime = favorite_price_regime(favorite_odds)
            opening = _market_probs(obs.base)
            closing = closing_probability(obs)
            predicted_move = _predict_movement(model, obs)
            record = {
                "observation": obs,
                "opening": opening,
                "closing": closing,
                "actual_move": actual_movement(obs),
                "predicted_move": predicted_move,
            }
            season_records[regime].append(record)
            overall_records[regime].append(record)

        season_reports.append(
            {
                "test_season_start_year": test_season,
                "training_seasons": training_seasons,
                "train_matches": len(train),
                "test_matches": len(test),
                "regimes": {name: _bucket_summary(season_records[name]) for name in REGIME_ORDER},
            }
        )

    return {
        "observer": "random_forest_closing_movement_by_fixed_market_regime_v1",
        "status": "historical_retrospective_subgroup_observer_zero_live_weight",
        "regime_definitions": REGIME_DEFINITIONS,
        "regime_policy": (
            "Reuses the pre-declared favorite-price bands unchanged: very_short <1.50; short 1.50-<1.80; "
            "moderate 1.80-2.20 inclusive; open >2.20. No boundary selection follows this audit."
        ),
        "split_policy": "Random Forest closing-movement model is walk-forward by closing-price season and uses only earlier closing-price seasons",
        "target": "de-vigged Bet365 closing probability minus de-vigged Bet365 first/pre-closing probability",
        "promotion_rule": (
            "This segmentation is retrospective context only. No regime, movement direction, price-timing rule, or threshold may be promoted from these inspected results. "
            "Any candidate hypothesis must be frozen and tested on later prospective bookmaker snapshots."
        ),
        "matches": sum(len(overall_records[name]) for name in REGIME_ORDER),
        "test_seasons": [report["test_season_start_year"] for report in season_reports],
        "overall_regimes": {name: _bucket_summary(overall_records[name]) for name in REGIME_ORDER},
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit RF closing-line movement by fixed market favorite-price regime.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-closing-seasons", type=int, default=DEFAULT_MIN_TRAIN_CLOSING_SEASONS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_market_regime_movement_audit(
        args.database,
        min_train_closing_seasons=args.min_train_closing_seasons,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote market-regime movement audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
