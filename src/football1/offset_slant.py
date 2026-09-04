from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from sklearn.preprocessing import StandardScaler

from football1.features import FEATURE_NAMES, FeatureRow, build_feature_rows, feature_vector
from football1.market_baseline import devig_decimal_odds
from football1.model_baseline import _mean_metrics, _top_label_ece


CLASS_INDEX = {"H": 0, "D": 1, "A": 2}


@dataclass
class OffsetSlantModel:
    scaler: StandardScaler
    intercept_h: float
    intercept_a: float
    coef_h: np.ndarray
    coef_a: np.ndarray
    alpha: float

    def predict_with_base(
        self,
        row: FeatureRow,
        base_probability: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        """Apply the frozen football residual to an explicit market baseline.

        Historical evaluation passes de-vigged Bet365 probabilities. Prospective
        evaluation may pass a separately documented live market consensus. The
        caller is responsible for recording that anchor-source change.
        """
        base = np.asarray(base_probability, dtype=float)
        if base.shape != (3,) or not np.all(np.isfinite(base)) or np.any(base <= 0):
            raise ValueError("base_probability must contain three positive finite values")
        total = float(base.sum())
        if abs(total - 1.0) > 1e-9:
            raise ValueError("base_probability must sum to 1")
        x = self.scaler.transform([feature_vector(row)])[0]
        logits = np.log(base)
        logits[0] += self.intercept_h + float(x @ self.coef_h)
        logits[2] += self.intercept_a + float(x @ self.coef_a)
        logits -= np.max(logits)
        exp = np.exp(logits)
        probs = exp / exp.sum()
        return (float(probs[0]), float(probs[1]), float(probs[2]))

    def predict(self, row: FeatureRow) -> tuple[float, float, float]:
        return self.predict_with_base(row, _market_probs(row))


@dataclass
class OffsetCalibrationModel:
    intercept_h: float
    intercept_a: float

    def predict(self, row: FeatureRow) -> tuple[float, float, float]:
        base = np.asarray(_market_probs(row), dtype=float)
        logits = np.log(base)
        logits[0] += self.intercept_h
        logits[2] += self.intercept_a
        logits -= np.max(logits)
        exp = np.exp(logits)
        probs = exp / exp.sum()
        return (float(probs[0]), float(probs[1]), float(probs[2]))


def _market_probs(row: FeatureRow) -> tuple[float, float, float]:
    if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
        raise ValueError(f"Missing Bet365 pre-closing odds for {row.match_id}")
    return devig_decimal_odds((row.b365_home, row.b365_draw, row.b365_away))[0]


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def fit_offset_calibration(rows: list[FeatureRow]) -> OffsetCalibrationModel:
    base = np.asarray([_market_probs(r) for r in rows], dtype=float)
    y = np.asarray([CLASS_INDEX[r.result] for r in rows], dtype=int)

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        logits = np.log(base).copy()
        logits[:, 0] += theta[0]
        logits[:, 2] += theta[1]
        probs = _softmax(logits)
        loss = -np.mean(np.log(probs[np.arange(len(y)), y]))
        residual = probs.copy()
        residual[np.arange(len(y)), y] -= 1.0
        grad = np.asarray([residual[:, 0].mean(), residual[:, 2].mean()])
        return float(loss), grad

    result = minimize(
        lambda t: objective(t)[0],
        np.zeros(2, dtype=float),
        jac=lambda t: objective(t)[1],
        method="L-BFGS-B",
    )
    if not result.success:
        raise RuntimeError(f"Offset calibration optimization failed: {result.message}")
    return OffsetCalibrationModel(float(result.x[0]), float(result.x[1]))


def fit_offset_slant(rows: list[FeatureRow], *, alpha: float) -> OffsetSlantModel:
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    x_raw = np.asarray([feature_vector(r) for r in rows], dtype=float)
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
        lambda t: objective(t)[0],
        np.zeros(2 + 2 * p, dtype=float),
        jac=lambda t: objective(t)[1],
        method="L-BFGS-B",
        options={"maxiter": 3000},
    )
    if not result.success:
        raise RuntimeError(f"Offset slant optimization failed: {result.message}")
    b_h, b_a, w_h, w_a = unpack(result.x)
    return OffsetSlantModel(scaler, b_h, b_a, w_h.copy(), w_a.copy(), alpha)


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def _score(model, rows: list[FeatureRow]) -> tuple[dict[str, float | int | None], list[tuple[tuple[float, float, float], str]]]:
    items = [(model.predict(r), r.result) for r in rows]
    metrics = _mean_metrics(items)
    metrics["top_label_ece"] = _top_label_ece(items)
    return metrics, items


def _score_raw(rows: list[FeatureRow]) -> tuple[dict[str, float | int | None], list[tuple[tuple[float, float, float], str]]]:
    items = [(_market_probs(r), r.result) for r in rows]
    metrics = _mean_metrics(items)
    metrics["top_label_ece"] = _top_label_ece(items)
    return metrics, items


def walk_forward_offset_slant(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = 0.10,
) -> dict[str, object]:
    """Residual slant around fixed Bet365 probabilities.

    Bet365's de-vigged log-probabilities are an immutable offset. Football
    features may only add H-vs-D and A-vs-D residual logits. Zero intercepts
    and zero football weights reproduce the raw market exactly.
    """
    rows = build_feature_rows(db_path)
    seasons = sorted({r.season_start_year for r in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_raw: list[tuple[tuple[float, float, float], str]] = []
    all_cal: list[tuple[tuple[float, float, float], str]] = []
    all_slant: list[tuple[tuple[float, float, float], str]] = []
    reports: list[dict[str, object]] = []
    latest_weights: dict[str, object] | None = None

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train = [r for r in rows if r.season_start_year in seasons[:test_index]]
        test = [r for r in rows if r.season_start_year == test_season]

        calibration = fit_offset_calibration(train)
        slant_model = fit_offset_slant(train, alpha=alpha)

        raw_m, raw_items = _score_raw(test)
        cal_m, cal_items = _score(calibration, test)
        slant_m, slant_items = _score(slant_model, test)
        all_raw.extend(raw_items)
        all_cal.extend(cal_items)
        all_slant.extend(slant_items)

        reports.append(
            {
                "test_season_start_year": test_season,
                "train_matches": len(train),
                "test_matches": len(test),
                "raw_market": raw_m,
                "offset_calibration": {
                    **cal_m,
                    "log_loss_delta_vs_raw": _delta(cal_m["log_loss"], raw_m["log_loss"]),
                    "brier_delta_vs_raw": _delta(cal_m["brier"], raw_m["brier"]),
                },
                "offset_football_slant": {
                    **slant_m,
                    "log_loss_delta_vs_raw": _delta(slant_m["log_loss"], raw_m["log_loss"]),
                    "log_loss_delta_vs_calibration": _delta(slant_m["log_loss"], cal_m["log_loss"]),
                    "brier_delta_vs_raw": _delta(slant_m["brier"], raw_m["brier"]),
                    "brier_delta_vs_calibration": _delta(slant_m["brier"], cal_m["brier"]),
                },
            }
        )

        if test_index == len(seasons) - 1:
            latest_weights = {
                "intercept_h": slant_model.intercept_h,
                "intercept_a": slant_model.intercept_a,
                "home_vs_draw": {name: float(v) for name, v in zip(FEATURE_NAMES, slant_model.coef_h)},
                "away_vs_draw": {name: float(v) for name, v in zip(FEATURE_NAMES, slant_model.coef_a)},
            }

    raw = _mean_metrics(all_raw)
    raw["top_label_ece"] = _top_label_ece(all_raw)
    cal = _mean_metrics(all_cal)
    cal["top_label_ece"] = _top_label_ece(all_cal)
    slant = _mean_metrics(all_slant)
    slant["top_label_ece"] = _top_label_ece(all_slant)

    return {
        "model": "fixed_market_offset_football_slant_v1",
        "market_source": "B365 pre-closing, de-vigged",
        "feature_names": list(FEATURE_NAMES),
        "alpha": alpha,
        "hyperparameter_policy": "alpha=0.10 fixed before this model's OOS evaluation; no OOS tuning",
        "split_policy": "walk-forward by season; training uses only earlier seasons",
        "same_day_policy": "all football features for a date snapshotted before results on that date",
        "overall_raw_market": raw,
        "overall_offset_calibration": {
            **cal,
            "log_loss_delta_vs_raw": _delta(cal["log_loss"], raw["log_loss"]),
            "brier_delta_vs_raw": _delta(cal["brier"], raw["brier"]),
        },
        "overall_offset_football_slant": {
            **slant,
            "log_loss_delta_vs_raw": _delta(slant["log_loss"], raw["log_loss"]),
            "log_loss_delta_vs_calibration": _delta(slant["log_loss"], cal["log_loss"]),
            "brier_delta_vs_raw": _delta(slant["brier"], raw["brier"]),
            "brier_delta_vs_calibration": _delta(slant["brier"], cal["brier"]),
        },
        "latest_standardized_residual_weights": latest_weights,
        "seasons": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Walk-forward residual slant around fixed bookmaker probabilities.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=0.10)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_offset_slant(
        args.database,
        min_train_seasons=args.min_train_seasons,
        alpha=args.alpha,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote fixed-market offset slant report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
