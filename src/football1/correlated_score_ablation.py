from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from sklearn.preprocessing import StandardScaler

from football1.correlated_score import CorrelatedPrediction, season_start_prediction_map
from football1.features import FEATURE_NAMES, FeatureRow, build_feature_rows, feature_vector
from football1.model_baseline import _mean_metrics, _top_label_ece
from football1.offset_slant import CLASS_INDEX, _market_probs, _softmax


ALPHA = 0.10
BASELINE = "frozen_residual_v1"
PLUS_BIVARIATE = "frozen_residual_plus_bivariate_poisson_v1"
PLUS_FRAILTY = "frozen_residual_plus_gamma_frailty_v1"
VARIANTS = (BASELINE, PLUS_BIVARIATE, PLUS_FRAILTY)
DEPENDENCE_FEATURE_NAMES = ("log_h_vs_d", "log_a_vs_d", "available")


@dataclass
class AblationModel:
    variant: str
    scaler: StandardScaler
    intercept_h: float
    intercept_a: float
    coef_h: np.ndarray
    coef_a: np.ndarray
    alpha: float


def variant_feature_names(variant: str) -> tuple[str, ...]:
    if variant == BASELINE:
        return FEATURE_NAMES
    if variant == PLUS_BIVARIATE:
        return FEATURE_NAMES + tuple(
            f"bivariate_poisson__{name}" for name in DEPENDENCE_FEATURE_NAMES
        )
    if variant == PLUS_FRAILTY:
        return FEATURE_NAMES + tuple(
            f"gamma_frailty__{name}" for name in DEPENDENCE_FEATURE_NAMES
        )
    raise ValueError(f"Unknown variant: {variant!r}")


def _prob_vector(probs: tuple[float, float, float] | None) -> list[float]:
    if probs is None:
        return [0.0, 0.0, 0.0]
    eps = 1e-12
    draw = max(probs[1], eps)
    return [
        math.log(max(probs[0], eps) / draw),
        math.log(max(probs[2], eps) / draw),
        1.0,
    ]


def variant_vector(
    row: FeatureRow,
    variant: str,
    prediction_by_match: dict[str, CorrelatedPrediction],
) -> list[float]:
    base = feature_vector(row)
    if variant == BASELINE:
        return base
    prediction = prediction_by_match.get(row.match_id)
    if variant == PLUS_BIVARIATE:
        return base + _prob_vector(None if prediction is None else prediction.bivariate_probs)
    if variant == PLUS_FRAILTY:
        return base + _prob_vector(None if prediction is None else prediction.frailty_probs)
    raise ValueError(f"Unknown variant: {variant!r}")


def fit_variant(
    rows: list[FeatureRow],
    *,
    variant: str,
    prediction_by_match: dict[str, CorrelatedPrediction],
    alpha: float = ALPHA,
) -> AblationModel:
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    x_raw = np.asarray(
        [variant_vector(row, variant, prediction_by_match) for row in rows], dtype=float
    )
    scaler = StandardScaler().fit(x_raw)
    x = scaler.transform(x_raw)
    base = np.asarray([_market_probs(row) for row in rows], dtype=float)
    y = np.asarray([CLASS_INDEX[row.result] for row in rows], dtype=int)
    n, p = x.shape

    def unpack(theta: np.ndarray) -> tuple[float, float, np.ndarray, np.ndarray]:
        return float(theta[0]), float(theta[1]), theta[2 : 2 + p], theta[2 + p :]

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        b_h, b_a, w_h, w_a = unpack(theta)
        logits = np.log(base).copy()
        logits[:, 0] += b_h + x @ w_h
        logits[:, 2] += b_a + x @ w_a
        probs = _softmax(logits)
        nll = -np.mean(np.log(probs[np.arange(n), y]))
        penalty = 0.5 * alpha * (float(w_h @ w_h) + float(w_a @ w_a))
        residual = probs.copy()
        residual[np.arange(n), y] -= 1.0
        grad = np.concatenate(
            (
                [residual[:, 0].mean(), residual[:, 2].mean()],
                (x.T @ residual[:, 0]) / n + alpha * w_h,
                (x.T @ residual[:, 2]) / n + alpha * w_a,
            )
        )
        return float(nll + penalty), grad

    result = minimize(
        lambda theta: objective(theta)[0],
        np.zeros(2 + 2 * p, dtype=float),
        jac=lambda theta: objective(theta)[1],
        method="L-BFGS-B",
        options={"maxiter": 3000},
    )
    if not result.success:
        raise RuntimeError(f"Correlated-score ablation optimization failed: {result.message}")
    b_h, b_a, w_h, w_a = unpack(result.x)
    return AblationModel(
        variant=variant,
        scaler=scaler,
        intercept_h=b_h,
        intercept_a=b_a,
        coef_h=w_h.copy(),
        coef_a=w_a.copy(),
        alpha=alpha,
    )


def predict_variant(
    model: AblationModel,
    row: FeatureRow,
    prediction_by_match: dict[str, CorrelatedPrediction],
) -> tuple[float, float, float]:
    base = np.asarray(_market_probs(row), dtype=float)
    x = model.scaler.transform(
        [variant_vector(row, model.variant, prediction_by_match)]
    )[0]
    logits = np.log(base)
    logits[0] += model.intercept_h + float(x @ model.coef_h)
    logits[2] += model.intercept_a + float(x @ model.coef_a)
    logits -= np.max(logits)
    exp = np.exp(logits)
    probs = exp / exp.sum()
    return float(probs[0]), float(probs[1]), float(probs[2])


def _metrics(
    items: list[tuple[tuple[float, float, float], str]],
) -> dict[str, float | int | None]:
    result = _mean_metrics(items)
    result["top_label_ece"] = _top_label_ece(items)
    return result


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def walk_forward_correlated_score_ablation(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = ALPHA,
) -> dict[str, object]:
    rows = build_feature_rows(db_path)
    prediction_by_match = season_start_prediction_map(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_raw: list[tuple[tuple[float, float, float], str]] = []
    all_items: dict[str, list[tuple[tuple[float, float, float], str]]] = {
        variant: [] for variant in VARIANTS
    }
    reports: list[dict[str, object]] = []
    latest_weights: dict[str, object] = {}

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train = [row for row in rows if row.season_start_year in seasons[:test_index]]
        test = [row for row in rows if row.season_start_year == test_season]
        raw_items = [(_market_probs(row), row.result) for row in test]
        raw_m = _metrics(raw_items)
        all_raw.extend(raw_items)
        season_variants: dict[str, object] = {}

        for variant in VARIANTS:
            model = fit_variant(
                train,
                variant=variant,
                prediction_by_match=prediction_by_match,
                alpha=alpha,
            )
            items = [
                (predict_variant(model, row, prediction_by_match), row.result)
                for row in test
            ]
            all_items[variant].extend(items)
            metrics = _metrics(items)
            season_variants[variant] = {
                **metrics,
                "log_loss_delta_vs_raw": _delta(
                    metrics["log_loss"], raw_m["log_loss"]
                ),
                "brier_delta_vs_raw": _delta(metrics["brier"], raw_m["brier"]),
            }
            if test_index == len(seasons) - 1:
                names = variant_feature_names(variant)
                latest_weights[variant] = {
                    "intercept_h": model.intercept_h,
                    "intercept_a": model.intercept_a,
                    "home_vs_draw": {
                        name: float(value) for name, value in zip(names, model.coef_h)
                    },
                    "away_vs_draw": {
                        name: float(value) for name, value in zip(names, model.coef_a)
                    },
                }
        reports.append(
            {
                "test_season_start_year": test_season,
                "train_matches": len(train),
                "test_matches": len(test),
                "raw_market": raw_m,
                "variants": season_variants,
            }
        )

    raw = _metrics(all_raw)
    overall: dict[str, object] = {}
    for variant in VARIANTS:
        metrics = _metrics(all_items[variant])
        overall[variant] = {
            **metrics,
            "feature_names": list(variant_feature_names(variant)),
            "log_loss_delta_vs_raw": _delta(metrics["log_loss"], raw["log_loss"]),
            "brier_delta_vs_raw": _delta(metrics["brier"], raw["brier"]),
        }

    baseline = overall[BASELINE]
    bivariate = overall[PLUS_BIVARIATE]
    frailty = overall[PLUS_FRAILTY]
    return {
        "experiment": "market_anchored_correlated_score_ablation_v1",
        "market_source": "B365 pre-closing, de-vigged immutable offset",
        "alpha": alpha,
        "baseline_policy": "the original inspected fixed-market residual v1 is preserved exactly",
        "feature_policy": (
            "base expected goals are leakage-safe pre-match rolling values; dependence parameters are frozen at each season start using only earlier seasons"
        ),
        "hyperparameter_policy": "all correlated-score v1 bounds and alpha=0.10 fixed before OOS; no OOS tuning",
        "overall_raw_market": raw,
        "overall_variants": overall,
        "incremental": {
            "plus_bivariate_minus_baseline_log_loss": _delta(
                bivariate["log_loss"], baseline["log_loss"]
            ),
            "plus_bivariate_minus_baseline_brier": _delta(
                bivariate["brier"], baseline["brier"]
            ),
            "plus_frailty_minus_baseline_log_loss": _delta(
                frailty["log_loss"], baseline["log_loss"]
            ),
            "plus_frailty_minus_baseline_brier": _delta(
                frailty["brier"], baseline["brier"]
            ),
        },
        "latest_standardized_weights": latest_weights,
        "seasons": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test correlated score information inside the frozen Football 1 market residual."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/processed/football1.sqlite"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_correlated_score_ablation(
        args.database,
        min_train_seasons=args.min_train_seasons,
        alpha=args.alpha,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote correlated-score ablation report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
