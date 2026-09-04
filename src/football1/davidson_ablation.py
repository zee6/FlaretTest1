from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from sklearn.preprocessing import StandardScaler

from football1.davidson import fit_davidson, load_matches, predict_probs
from football1.features import FEATURE_NAMES, FeatureRow, build_feature_rows, feature_vector
from football1.model_baseline import _mean_metrics, _top_label_ece
from football1.offset_slant import CLASS_INDEX, _market_probs, _softmax


ALPHA = 0.10
BASELINE = "frozen_residual_v1"
PLUS_DAVIDSON = "frozen_residual_plus_davidson_v1"
VARIANTS = (BASELINE, PLUS_DAVIDSON)
DAVIDSON_FEATURE_NAMES = ("davidson_log_h_vs_d", "davidson_log_a_vs_d", "davidson_available")


@dataclass
class AblationModel:
    variant: str
    scaler: StandardScaler
    intercept_h: float
    intercept_a: float
    coef_h: np.ndarray
    coef_a: np.ndarray
    alpha: float


def build_leakage_safe_davidson_map(db_path: Path) -> dict[str, tuple[float, float, float, float]]:
    """Return per-match Davidson features generated only from earlier seasons."""
    matches = load_matches(db_path)
    seasons = sorted({m.season_start_year for m in matches})
    out: dict[str, tuple[float, float, float, float]] = {}
    eps = 1e-12
    for i, season in enumerate(seasons):
        current = [m for m in matches if m.season_start_year == season]
        if i == 0:
            for m in current:
                out[m.match_id] = (0.0, 0.0, 0.0, 0.0)
            continue
        train = [m for m in matches if m.season_start_year in seasons[:i]]
        model = fit_davidson(train)
        for m in current:
            h, d, a = predict_probs(model, m.home_team, m.away_team)
            out[m.match_id] = (
                math.log(max(h, eps) / max(d, eps)),
                math.log(max(a, eps) / max(d, eps)),
                1.0,
                float(season),
            )
    return out


def variant_feature_names(variant: str) -> tuple[str, ...]:
    if variant == BASELINE:
        return FEATURE_NAMES
    if variant == PLUS_DAVIDSON:
        return FEATURE_NAMES + tuple(f"davidson__{name}" for name in DAVIDSON_FEATURE_NAMES)
    raise ValueError(f"Unknown variant: {variant!r}")


def variant_vector(
    row: FeatureRow,
    variant: str,
    davidson_by_match: dict[str, tuple[float, float, float, float]],
) -> list[float]:
    base = feature_vector(row)
    if variant == BASELINE:
        return base
    if variant == PLUS_DAVIDSON:
        try:
            h_vs_d, a_vs_d, available, season = davidson_by_match[row.match_id]
        except KeyError as exc:
            raise ValueError(f"Missing Davidson state for {row.match_id}") from exc
        if int(season) not in (0, row.season_start_year):
            raise ValueError("Davidson season mismatch")
        return base + [h_vs_d, a_vs_d, available]
    raise ValueError(f"Unknown variant: {variant!r}")


def fit_variant(
    rows: list[FeatureRow],
    *,
    variant: str,
    davidson_by_match: dict[str, tuple[float, float, float, float]],
    alpha: float = ALPHA,
) -> AblationModel:
    x_raw = np.asarray([variant_vector(r, variant, davidson_by_match) for r in rows], dtype=float)
    scaler = StandardScaler().fit(x_raw)
    x = scaler.transform(x_raw)
    base = np.asarray([_market_probs(r) for r in rows], dtype=float)
    y = np.asarray([CLASS_INDEX[r.result] for r in rows], dtype=int)
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
        grad = np.concatenate((
            [residual[:, 0].mean(), residual[:, 2].mean()],
            (x.T @ residual[:, 0]) / n + alpha * w_h,
            (x.T @ residual[:, 2]) / n + alpha * w_a,
        ))
        return float(nll + penalty), grad

    result = minimize(
        lambda theta: objective(theta)[0],
        np.zeros(2 + 2 * p, dtype=float),
        jac=lambda theta: objective(theta)[1],
        method="L-BFGS-B",
        options={"maxiter": 3000},
    )
    if not result.success:
        raise RuntimeError(f"Davidson ablation optimization failed: {result.message}")
    b_h, b_a, w_h, w_a = unpack(result.x)
    return AblationModel(variant, scaler, b_h, b_a, w_h.copy(), w_a.copy(), alpha)


def predict_variant(
    model: AblationModel,
    row: FeatureRow,
    davidson_by_match: dict[str, tuple[float, float, float, float]],
) -> tuple[float, float, float]:
    base = np.asarray(_market_probs(row), dtype=float)
    x = model.scaler.transform([variant_vector(row, model.variant, davidson_by_match)])[0]
    logits = np.log(base)
    logits[0] += model.intercept_h + float(x @ model.coef_h)
    logits[2] += model.intercept_a + float(x @ model.coef_a)
    logits -= np.max(logits)
    exp = np.exp(logits)
    p = exp / exp.sum()
    return (float(p[0]), float(p[1]), float(p[2]))


def _metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    result = _mean_metrics(items)
    result["top_label_ece"] = _top_label_ece(items)
    return result


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def walk_forward_davidson_ablation(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = ALPHA,
) -> dict[str, object]:
    rows = build_feature_rows(db_path)
    davidson_by_match = build_leakage_safe_davidson_map(db_path)
    seasons = sorted({r.season_start_year for r in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons")

    all_raw: list[tuple[tuple[float, float, float], str]] = []
    all_items = {variant: [] for variant in VARIANTS}
    reports: list[dict[str, object]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train = [r for r in rows if r.season_start_year in seasons[:test_index]]
        test = [r for r in rows if r.season_start_year == test_season]
        raw_items = [(_market_probs(r), r.result) for r in test]
        raw_m = _metrics(raw_items)
        all_raw.extend(raw_items)
        variants: dict[str, object] = {}
        for variant in VARIANTS:
            model = fit_variant(train, variant=variant, davidson_by_match=davidson_by_match, alpha=alpha)
            items = [(predict_variant(model, r, davidson_by_match), r.result) for r in test]
            all_items[variant].extend(items)
            m = _metrics(items)
            variants[variant] = {
                **m,
                "log_loss_delta_vs_raw": _delta(m["log_loss"], raw_m["log_loss"]),
                "brier_delta_vs_raw": _delta(m["brier"], raw_m["brier"]),
            }
        reports.append({
            "test_season_start_year": test_season,
            "train_matches": len(train),
            "test_matches": len(test),
            "raw_market": raw_m,
            "variants": variants,
        })

    raw = _metrics(all_raw)
    overall: dict[str, object] = {}
    for variant in VARIANTS:
        m = _metrics(all_items[variant])
        overall[variant] = {
            **m,
            "feature_names": list(variant_feature_names(variant)),
            "log_loss_delta_vs_raw": _delta(m["log_loss"], raw["log_loss"]),
            "brier_delta_vs_raw": _delta(m["brier"], raw["brier"]),
        }
    baseline = overall[BASELINE]
    challenger = overall[PLUS_DAVIDSON]
    return {
        "experiment": "market_anchored_davidson_ablation_v1",
        "market_source": "B365 pre-closing, de-vigged immutable offset",
        "alpha": alpha,
        "hyperparameter_policy": "residual alpha and Davidson v1 frozen before OOS evaluation; no OOS tuning",
        "leakage_policy": "each Davidson feature is generated by a model fit only on seasons earlier than that feature's match",
        "overall_raw_market": raw,
        "overall_variants": overall,
        "incremental": {
            "plus_davidson_minus_baseline_log_loss": _delta(challenger["log_loss"], baseline["log_loss"]),
            "plus_davidson_minus_baseline_brier": _delta(challenger["brier"], baseline["brier"]),
            "plus_davidson_minus_baseline_ece": _delta(challenger["top_label_ece"], baseline["top_label_ece"]),
        },
        "seasons": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ablate Davidson paired-comparison information inside the frozen market residual.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_davidson_ablation(args.database, min_train_seasons=args.min_train_seasons, alpha=args.alpha)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote Davidson ablation report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
