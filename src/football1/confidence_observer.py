from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Callable

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from football1.model_disagreement import DisagreementRow, build_disagreement_rows


META_MIN_TRAIN_SEASONS = 3
EPS = 1e-6


def _clip_probability(value: float) -> float:
    return min(1.0 - EPS, max(EPS, float(value)))


def _logit(value: float) -> float:
    p = _clip_probability(value)
    return math.log(p / (1.0 - p))


def _market_top_probability(row: DisagreementRow) -> float:
    return max(row.market_probs)


def _market_top_correct(row: DisagreementRow) -> int:
    return int(row.market_top == row.result)


def _binary_metrics(probabilities: list[float], targets: list[int]) -> dict[str, float | int | None]:
    if not probabilities:
        return {
            "matches": 0,
            "log_loss": None,
            "brier": None,
            "accuracy": None,
            "mean_predicted_confidence": None,
            "observed_correct_rate": None,
            "calibration_gap": None,
        }
    if len(probabilities) != len(targets):
        raise ValueError("probabilities and targets must have the same length")

    probs = [_clip_probability(p) for p in probabilities]
    n = len(probs)
    log_loss = -sum(
        y * math.log(p) + (1 - y) * math.log(1.0 - p)
        for p, y in zip(probs, targets)
    ) / n
    brier = sum((p - y) ** 2 for p, y in zip(probs, targets)) / n
    accuracy = sum(int((p >= 0.5) == bool(y)) for p, y in zip(probs, targets)) / n
    mean_p = sum(probs) / n
    observed = sum(targets) / n
    return {
        "matches": n,
        "log_loss": log_loss,
        "brier": brier,
        "accuracy": accuracy,
        "mean_predicted_confidence": mean_p,
        "observed_correct_rate": observed,
        "calibration_gap": observed - mean_p,
    }


def _market_only_features(row: DisagreementRow) -> list[float]:
    return [_logit(_market_top_probability(row))]


def _market_plus_alignment_features(row: DisagreementRow) -> list[float]:
    return [
        _logit(_market_top_probability(row)),
        row.market_alignment_count / 4.0,
    ]


def _market_plus_disagreement_features(row: DisagreementRow) -> list[float]:
    return [
        _logit(_market_top_probability(row)),
        row.market_alignment_count / 4.0,
        row.shadow_consensus_count / 4.0,
        row.probability_dispersion,
        row.mean_abs_shadow_market_distance,
    ]


FEATURE_SETS: dict[str, tuple[list[str], Callable[[DisagreementRow], list[float]]]] = {
    "market_recalibrated": (
        ["market_top_logit"],
        _market_only_features,
    ),
    "market_plus_alignment": (
        ["market_top_logit", "shadow_market_alignment_fraction"],
        _market_plus_alignment_features,
    ),
    "market_plus_full_disagreement": (
        [
            "market_top_logit",
            "shadow_market_alignment_fraction",
            "shadow_consensus_fraction",
            "shadow_probability_dispersion",
            "mean_abs_shadow_market_distance",
        ],
        _market_plus_disagreement_features,
    ),
}


def _fit_meta_model(
    rows: list[DisagreementRow],
    feature_fn: Callable[[DisagreementRow], list[float]],
) -> Pipeline:
    targets = [_market_top_correct(row) for row in rows]
    if len(set(targets)) < 2:
        raise ValueError("Meta-model training data must contain both correct and incorrect market top calls")
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "logistic",
                LogisticRegression(
                    solver="lbfgs",
                    C=1.0,
                    max_iter=2000,
                    random_state=0,
                ),
            ),
        ]
    )
    x = np.asarray([feature_fn(row) for row in rows], dtype=float)
    model.fit(x, targets)
    return model


def _predict_meta_model(
    model: Pipeline,
    rows: list[DisagreementRow],
    feature_fn: Callable[[DisagreementRow], list[float]],
) -> list[float]:
    if not rows:
        return []
    x = np.asarray([feature_fn(row) for row in rows], dtype=float)
    return [float(p) for p in model.predict_proba(x)[:, 1]]


def _metric_delta(
    challenger: dict[str, float | int | None],
    baseline: dict[str, float | int | None],
) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for name in ("log_loss", "brier"):
        a = challenger[name]
        b = baseline[name]
        result[name] = float(a) - float(b) if a is not None and b is not None else None
    return result


def walk_forward_confidence_from_rows(
    rows: list[DisagreementRow],
    *,
    meta_min_train_seasons: int = META_MIN_TRAIN_SEASONS,
) -> dict[str, object]:
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= meta_min_train_seasons:
        raise ValueError("Not enough OOS seasons for the meta-confidence walk-forward")

    overall_targets: list[int] = []
    overall_raw_market: list[float] = []
    overall_predictions: dict[str, list[float]] = {name: [] for name in FEATURE_SETS}
    season_reports: list[dict[str, object]] = []

    for test_index in range(meta_min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train_seasons = set(seasons[:test_index])
        train_rows = [row for row in rows if row.season_start_year in train_seasons]
        test_rows = [row for row in rows if row.season_start_year == test_season]
        if not test_rows:
            continue

        targets = [_market_top_correct(row) for row in test_rows]
        raw_market = [_market_top_probability(row) for row in test_rows]
        raw_metrics = _binary_metrics(raw_market, targets)
        fitted_metrics: dict[str, dict[str, float | int | None]] = {}

        for name, (_, feature_fn) in FEATURE_SETS.items():
            model = _fit_meta_model(train_rows, feature_fn)
            predictions = _predict_meta_model(model, test_rows, feature_fn)
            overall_predictions[name].extend(predictions)
            fitted_metrics[name] = _binary_metrics(predictions, targets)

        overall_targets.extend(targets)
        overall_raw_market.extend(raw_market)
        season_reports.append(
            {
                "test_season_start_year": test_season,
                "train_oos_seasons": sorted(train_seasons),
                "train_matches": len(train_rows),
                "test_matches": len(test_rows),
                "raw_market_top_probability": raw_metrics,
                **fitted_metrics,
                "incremental_vs_market_recalibrated": {
                    "market_plus_alignment": _metric_delta(
                        fitted_metrics["market_plus_alignment"],
                        fitted_metrics["market_recalibrated"],
                    ),
                    "market_plus_full_disagreement": _metric_delta(
                        fitted_metrics["market_plus_full_disagreement"],
                        fitted_metrics["market_recalibrated"],
                    ),
                },
            }
        )

    if not overall_targets:
        raise ValueError("No meta-confidence test rows were produced")

    overall: dict[str, dict[str, float | int | None]] = {
        "raw_market_top_probability": _binary_metrics(
            overall_raw_market, overall_targets
        )
    }
    for name, predictions in overall_predictions.items():
        overall[name] = _binary_metrics(predictions, overall_targets)

    return {
        "experiment": "market_top_confidence_observer_v1",
        "status": "historical_retrospective_observer_only_zero_decision_weight",
        "research_selection_status": (
            "This meta-confidence hypothesis was specified after inspecting the earlier "
            "shadow-disagreement observer. The computation is leakage-safe walk-forward, "
            "but the research idea is not prospectively untouched and cannot be promoted "
            "without fresh prospective confirmation."
        ),
        "question": (
            "Does agreement/disagreement among OOS shadow models add information about "
            "whether the market's most likely 1X2 outcome will be correct, after accounting "
            "for the market's own top-outcome probability?"
        ),
        "target": "binary indicator: de-vigged market top 1X2 outcome was correct",
        "base_prediction_policy": (
            "All shadow inputs come from the existing season-level OOS disagreement rows. "
            "The meta-model never receives an in-sample shadow prediction for its test season."
        ),
        "meta_split_policy": (
            "walk-forward over OOS seasons; each test season's confidence model is trained "
            "only on earlier OOS seasons"
        ),
        "model_policy": (
            "fixed StandardScaler + logistic regression (C=1.0, lbfgs); no hyperparameter "
            "or threshold tuning on held-out meta seasons"
        ),
        "feature_sets": {
            name: feature_names for name, (feature_names, _) in FEATURE_SETS.items()
        },
        "interpretation_policy": (
            "This models confidence/uncertainty only. It does not change the 1X2 probability, "
            "create a bet, choose a stake, or alter Football 1's live decision weight."
        ),
        "meta_min_train_seasons": meta_min_train_seasons,
        "overall": overall,
        "incremental_vs_market_recalibrated": {
            "market_plus_alignment": _metric_delta(
                overall["market_plus_alignment"], overall["market_recalibrated"]
            ),
            "market_plus_full_disagreement": _metric_delta(
                overall["market_plus_full_disagreement"],
                overall["market_recalibrated"],
            ),
        },
        "seasons": season_reports,
    }


def market_confidence_audit(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    meta_min_train_seasons: int = META_MIN_TRAIN_SEASONS,
) -> dict[str, object]:
    rows = build_disagreement_rows(db_path, min_train_seasons=min_train_seasons)
    return walk_forward_confidence_from_rows(
        rows, meta_min_train_seasons=meta_min_train_seasons
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Leakage-safe meta-observer for whether shadow-model disagreement adds "
            "information about the correctness of the market's top outcome."
        )
    )
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/football1.sqlite")
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument(
        "--meta-min-train-seasons", type=int, default=META_MIN_TRAIN_SEASONS
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = market_confidence_audit(
        args.database,
        min_train_seasons=args.min_train_seasons,
        meta_min_train_seasons=args.meta_min_train_seasons,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote market-confidence report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
