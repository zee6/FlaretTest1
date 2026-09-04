from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from sklearn.preprocessing import StandardScaler

from football1.elo import build_elo_rows
from football1.features import FEATURE_NAMES, FeatureRow, build_feature_rows
from football1.model_baseline import _mean_metrics, _top_label_ece
from football1.offset_slant import CLASS_INDEX, _market_probs, _softmax


ALPHA = 0.10
NON_ELO_FEATURE_NAMES = tuple(name for name in FEATURE_NAMES if name != "elo_diff")
VARIANTS = ("no_elo", "legacy_elo", "modular_elo_v1")


@dataclass
class VariantModel:
    variant: str
    scaler: StandardScaler
    intercept_h: float
    intercept_a: float
    coef_h: np.ndarray
    coef_a: np.ndarray
    alpha: float


def modular_elo_map(db_path: Path) -> dict[str, float]:
    """Return leakage-safe neutral-ground Elo strength differences by match."""
    return {
        row.match_id: row.home_rating - row.away_rating
        for row in build_elo_rows(db_path)
    }


def variant_feature_names(variant: str) -> tuple[str, ...]:
    if variant == "no_elo":
        return NON_ELO_FEATURE_NAMES
    if variant == "legacy_elo":
        return FEATURE_NAMES
    if variant == "modular_elo_v1":
        return NON_ELO_FEATURE_NAMES + ("modular_elo_strength_diff",)
    raise ValueError(f"Unknown variant: {variant!r}")


def variant_vector(row: FeatureRow, variant: str, elo_by_match: dict[str, float]) -> list[float]:
    values = [float(getattr(row, name)) for name in NON_ELO_FEATURE_NAMES]
    if variant == "no_elo":
        return values
    if variant == "legacy_elo":
        # Rebuild the original FEATURE_NAMES order exactly.
        return [float(getattr(row, name)) for name in FEATURE_NAMES]
    if variant == "modular_elo_v1":
        try:
            modular = elo_by_match[row.match_id]
        except KeyError as exc:
            raise ValueError(f"Missing modular Elo state for {row.match_id}") from exc
        return values + [float(modular)]
    raise ValueError(f"Unknown variant: {variant!r}")


def fit_variant(
    rows: list[FeatureRow],
    *,
    variant: str,
    elo_by_match: dict[str, float],
    alpha: float = ALPHA,
) -> VariantModel:
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    x_raw = np.asarray([variant_vector(row, variant, elo_by_match) for row in rows], dtype=float)
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
        loss = nll + penalty

        residual = probs.copy()
        residual[np.arange(n), y] -= 1.0
        grad_b_h = residual[:, 0].mean()
        grad_b_a = residual[:, 2].mean()
        grad_w_h = (x.T @ residual[:, 0]) / n + alpha * w_h
        grad_w_a = (x.T @ residual[:, 2]) / n + alpha * w_a
        grad = np.concatenate(([grad_b_h, grad_b_a], grad_w_h, grad_w_a))
        return float(loss), grad

    result = minimize(
        lambda theta: objective(theta)[0],
        np.zeros(2 + 2 * p, dtype=float),
        jac=lambda theta: objective(theta)[1],
        method="L-BFGS-B",
        options={"maxiter": 3000},
    )
    if not result.success:
        raise RuntimeError(f"Elo ablation optimization failed: {result.message}")
    b_h, b_a, w_h, w_a = unpack(result.x)
    return VariantModel(
        variant=variant,
        scaler=scaler,
        intercept_h=b_h,
        intercept_a=b_a,
        coef_h=w_h.copy(),
        coef_a=w_a.copy(),
        alpha=alpha,
    )


def predict_variant(
    model: VariantModel,
    row: FeatureRow,
    elo_by_match: dict[str, float],
) -> tuple[float, float, float]:
    base = np.asarray(_market_probs(row), dtype=float)
    x = model.scaler.transform([variant_vector(row, model.variant, elo_by_match)])[0]
    logits = np.log(base)
    logits[0] += model.intercept_h + float(x @ model.coef_h)
    logits[2] += model.intercept_a + float(x @ model.coef_a)
    logits -= np.max(logits)
    exp = np.exp(logits)
    probs = exp / exp.sum()
    return (float(probs[0]), float(probs[1]), float(probs[2]))


def _metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    result = _mean_metrics(items)
    result["top_label_ece"] = _top_label_ece(items)
    return result


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def walk_forward_elo_ablation(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = ALPHA,
) -> dict[str, object]:
    rows = build_feature_rows(db_path)
    elo_by_match = modular_elo_map(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_raw: list[tuple[tuple[float, float, float], str]] = []
    all_items: dict[str, list[tuple[tuple[float, float, float], str]]] = {
        variant: [] for variant in VARIANTS
    }
    reports: list[dict[str, object]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train = [row for row in rows if row.season_start_year in seasons[:test_index]]
        test = [row for row in rows if row.season_start_year == test_season]
        raw_items = [(_market_probs(row), row.result) for row in test]
        all_raw.extend(raw_items)
        raw_m = _metrics(raw_items)

        season_variants: dict[str, object] = {}
        for variant in VARIANTS:
            model = fit_variant(train, variant=variant, elo_by_match=elo_by_match, alpha=alpha)
            items = [(predict_variant(model, row, elo_by_match), row.result) for row in test]
            all_items[variant].extend(items)
            metrics = _metrics(items)
            season_variants[variant] = {
                **metrics,
                "log_loss_delta_vs_raw": _delta(metrics["log_loss"], raw_m["log_loss"]),
                "brier_delta_vs_raw": _delta(metrics["brier"], raw_m["brier"]),
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

    legacy = overall["legacy_elo"]
    no_elo = overall["no_elo"]
    modular = overall["modular_elo_v1"]

    return {
        "experiment": "market_anchored_elo_ablation_v1",
        "market_source": "B365 pre-closing, de-vigged immutable offset",
        "alpha": alpha,
        "hyperparameter_policy": "alpha and both Elo definitions frozen before this ablation; no OOS tuning",
        "comparison": "same residual architecture and football features; only Elo treatment changes",
        "legacy_elo_definition": "existing embedded feature: K=20, home advantage used in updates, no season regression",
        "modular_elo_definition": "Elo v1: K=20, 75-point home advantage in updates, 0.75 season carry; neutral-ground rating difference supplied to residual layer",
        "same_day_policy": "both feature systems snapshot all fixtures on a date before same-date result updates",
        "overall_raw_market": raw,
        "overall_variants": overall,
        "incremental_comparisons": {
            "legacy_vs_no_elo_log_loss": _delta(legacy["log_loss"], no_elo["log_loss"]),
            "modular_vs_no_elo_log_loss": _delta(modular["log_loss"], no_elo["log_loss"]),
            "modular_vs_legacy_log_loss": _delta(modular["log_loss"], legacy["log_loss"]),
            "legacy_vs_no_elo_brier": _delta(legacy["brier"], no_elo["brier"]),
            "modular_vs_no_elo_brier": _delta(modular["brier"], no_elo["brier"]),
            "modular_vs_legacy_brier": _delta(modular["brier"], legacy["brier"]),
        },
        "seasons": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ablate Elo inside the fixed-market residual model.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_elo_ablation(
        args.database,
        min_train_seasons=args.min_train_seasons,
        alpha=args.alpha,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote Elo ablation report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
