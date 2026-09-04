from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from football1.features import FEATURE_NAMES, FeatureRow, build_feature_rows, feature_vector
from football1.market_baseline import devig_decimal_odds
from football1.model_baseline import _mean_metrics, _top_label_ece


SLANT_FEATURE_NAMES = ("market_log_h_over_d", "market_log_a_over_d", *FEATURE_NAMES)
MARKET_CALIBRATION_FEATURE_NAMES = ("market_log_h_over_d", "market_log_a_over_d")


def market_probabilities(row: FeatureRow) -> tuple[float, float, float]:
    if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
        raise ValueError(f"Missing Bet365 pre-closing odds for {row.match_id}")
    return devig_decimal_odds((row.b365_home, row.b365_draw, row.b365_away))[0]


def market_log_ratio_features(row: FeatureRow) -> list[float]:
    h, d, a = market_probabilities(row)
    return [math.log(h / d), math.log(a / d)]


def slant_feature_vector(row: FeatureRow) -> list[float]:
    return [*market_log_ratio_features(row), *feature_vector(row)]


def _pipeline(c: float) -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            ("model", LogisticRegression(C=c, solver="lbfgs", max_iter=3000)),
        ]
    )


def _hda_probabilities(model: Pipeline, vector: list[float]) -> tuple[float, float, float]:
    raw = model.predict_proba([vector])[0]
    classes = list(model.named_steps["model"].classes_)
    mapping = {label: float(raw[i]) for i, label in enumerate(classes)}
    return (mapping["H"], mapping["D"], mapping["A"])


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def walk_forward_slant(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    c: float = 1.0,
) -> dict[str, object]:
    """Test whether football features add information beyond the market.

    For each OOS season, two models are independently fit on prior seasons:
      1. market-only calibration control using Bet365 de-vigged log ratios;
      2. slant model using the same market features plus football-only features.

    The raw de-vigged Bet365 probabilities are the third comparator. No OOS
    season is used to choose C or any other model hyperparameter.
    """
    rows = build_feature_rows(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for requested walk-forward evaluation")

    overall_raw: list[tuple[tuple[float, float, float], str]] = []
    overall_calibrated: list[tuple[tuple[float, float, float], str]] = []
    overall_slant: list[tuple[tuple[float, float, float], str]] = []
    season_reports: list[dict[str, object]] = []
    latest_coefficients: dict[str, dict[str, float]] | None = None

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        training_seasons = seasons[:test_index]
        train = [r for r in rows if r.season_start_year in training_seasons]
        test = [r for r in rows if r.season_start_year == test_season]

        # B365 pre-closing is expected to have full corpus coverage; fail hard
        # rather than silently changing the paired sample.
        for row in (*train, *test):
            market_probabilities(row)

        y_train = [r.result for r in train]
        market_control = _pipeline(c)
        market_control.fit([market_log_ratio_features(r) for r in train], y_train)

        slant = _pipeline(c)
        slant.fit([slant_feature_vector(r) for r in train], y_train)

        raw_items: list[tuple[tuple[float, float, float], str]] = []
        calibrated_items: list[tuple[tuple[float, float, float], str]] = []
        slant_items: list[tuple[tuple[float, float, float], str]] = []

        for row in test:
            raw_probs = market_probabilities(row)
            calibrated_probs = _hda_probabilities(market_control, market_log_ratio_features(row))
            slant_probs = _hda_probabilities(slant, slant_feature_vector(row))
            raw_items.append((raw_probs, row.result))
            calibrated_items.append((calibrated_probs, row.result))
            slant_items.append((slant_probs, row.result))
            overall_raw.append((raw_probs, row.result))
            overall_calibrated.append((calibrated_probs, row.result))
            overall_slant.append((slant_probs, row.result))

        raw_metrics = _mean_metrics(raw_items)
        calibrated_metrics = _mean_metrics(calibrated_items)
        slant_metrics = _mean_metrics(slant_items)
        season_reports.append(
            {
                "test_season_start_year": test_season,
                "training_seasons": training_seasons,
                "train_matches": len(train),
                "test_matches": len(test),
                "raw_market": {**raw_metrics, "top_label_ece": _top_label_ece(raw_items)},
                "market_only_calibration": {
                    **calibrated_metrics,
                    "top_label_ece": _top_label_ece(calibrated_items),
                    "log_loss_delta_vs_raw": _delta(calibrated_metrics["log_loss"], raw_metrics["log_loss"]),
                    "brier_delta_vs_raw": _delta(calibrated_metrics["brier"], raw_metrics["brier"]),
                },
                "market_plus_football_slant": {
                    **slant_metrics,
                    "top_label_ece": _top_label_ece(slant_items),
                    "log_loss_delta_vs_raw": _delta(slant_metrics["log_loss"], raw_metrics["log_loss"]),
                    "log_loss_delta_vs_market_only": _delta(slant_metrics["log_loss"], calibrated_metrics["log_loss"]),
                    "brier_delta_vs_raw": _delta(slant_metrics["brier"], raw_metrics["brier"]),
                    "brier_delta_vs_market_only": _delta(slant_metrics["brier"], calibrated_metrics["brier"]),
                },
            }
        )

        if test_index == len(seasons) - 1:
            classes = list(slant.named_steps["model"].classes_)
            coefficients = slant.named_steps["model"].coef_
            latest_coefficients = {
                str(label): {
                    name: float(coefficients[i][j])
                    for j, name in enumerate(SLANT_FEATURE_NAMES)
                }
                for i, label in enumerate(classes)
            }

    raw = _mean_metrics(overall_raw)
    calibrated = _mean_metrics(overall_calibrated)
    slant = _mean_metrics(overall_slant)
    return {
        "model": "market_conditioned_football_slant_v1",
        "market_source": "B365 pre-closing",
        "split_policy": "walk-forward by season; each OOS season predicted by models fit only on earlier seasons",
        "same_day_policy": "all football features for a date are snapshotted before any result on that date is applied",
        "hyperparameter_policy": "C=1.0 fixed before OOS evaluation; no OOS tuning",
        "market_calibration_feature_names": list(MARKET_CALIBRATION_FEATURE_NAMES),
        "slant_feature_names": list(SLANT_FEATURE_NAMES),
        "overall_raw_market": {**raw, "top_label_ece": _top_label_ece(overall_raw)},
        "overall_market_only_calibration": {
            **calibrated,
            "top_label_ece": _top_label_ece(overall_calibrated),
            "log_loss_delta_vs_raw": _delta(calibrated["log_loss"], raw["log_loss"]),
            "brier_delta_vs_raw": _delta(calibrated["brier"], raw["brier"]),
        },
        "overall_market_plus_football_slant": {
            **slant,
            "top_label_ece": _top_label_ece(overall_slant),
            "log_loss_delta_vs_raw": _delta(slant["log_loss"], raw["log_loss"]),
            "log_loss_delta_vs_market_only": _delta(slant["log_loss"], calibrated["log_loss"]),
            "brier_delta_vs_raw": _delta(slant["brier"], raw["brier"]),
            "brier_delta_vs_market_only": _delta(slant["brier"], calibrated["brier"]),
        },
        "latest_standardized_coefficients": latest_coefficients,
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Walk-forward test of market probability slanting with football features.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--c", type=float, default=1.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_slant(args.database, min_train_seasons=args.min_train_seasons, c=args.c)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote market slant report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
