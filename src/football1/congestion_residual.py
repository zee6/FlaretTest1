from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from sklearn.preprocessing import StandardScaler

from football1.features import FeatureRow, build_feature_rows
from football1.market_baseline import devig_decimal_odds
from football1.model_baseline import _mean_metrics, _top_label_ece
from football1.offset_slant import fit_offset_calibration


CLASS_INDEX = {"H": 0, "D": 1, "A": 2}
RESULTS = ("H", "D", "A")
CONGESTION_FEATURE_NAMES = (
    "home_rest_days",
    "away_rest_days",
    "home_matches_previous_7_days",
    "away_matches_previous_7_days",
    "home_matches_previous_14_days",
    "away_matches_previous_14_days",
)
DEFAULT_ALPHA = 0.10


@dataclass(frozen=True)
class CongestionRow:
    base: FeatureRow
    home_rest_days: float
    away_rest_days: float
    home_matches_previous_7_days: float
    away_matches_previous_7_days: float
    home_matches_previous_14_days: float
    away_matches_previous_14_days: float

    @property
    def result(self) -> str:
        return self.base.result

    @property
    def season_start_year(self) -> int:
        return self.base.season_start_year


@dataclass
class CongestionResidualModel:
    scaler: StandardScaler
    intercept_h: float
    intercept_a: float
    coef_h: np.ndarray
    coef_a: np.ndarray
    alpha: float

    def predict(self, row: CongestionRow) -> tuple[float, float, float]:
        market = np.asarray(_market_probs(row.base), dtype=float)
        x = self.scaler.transform([congestion_vector(row)])[0]
        logits = np.log(market)
        logits[0] += self.intercept_h + float(x @ self.coef_h)
        logits[2] += self.intercept_a + float(x @ self.coef_a)
        logits -= np.max(logits)
        exp = np.exp(logits)
        probs = exp / exp.sum()
        return (float(probs[0]), float(probs[1]), float(probs[2]))


def _market_probs(row: FeatureRow) -> tuple[float, float, float]:
    if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
        raise ValueError(f"Missing B365 H/D/A odds for {row.match_id}")
    return devig_decimal_odds((row.b365_home, row.b365_draw, row.b365_away))[0]


def _rest_days(history: list[date], current: date) -> float:
    if not history:
        return 7.0
    days = (current - history[-1]).days
    return float(max(0, min(days, 30)))


def _recent_count(history: list[date], current: date, window: int) -> float:
    return float(sum(1 for previous in history if 0 < (current - previous).days <= window))


def build_congestion_rows(db_path: Path) -> list[CongestionRow]:
    """Create schedule-only congestion features with same-date freezing.

    The source FeatureRows are already chronological and leakage-safe. For a
    calendar date, every fixture's rest/load features are calculated before any
    fixture on that date is appended to a team's schedule history. Historical
    files often lack trustworthy kickoff timestamps, so this conservative rule
    prevents same-day ordering from becoming information.
    """
    base_rows = build_feature_rows(db_path)
    histories: dict[str, list[date]] = defaultdict(list)
    result: list[CongestionRow] = []

    i = 0
    while i < len(base_rows):
        current_date = base_rows[i].match_date
        current = date.fromisoformat(current_date)
        j = i
        while j < len(base_rows) and base_rows[j].match_date == current_date:
            j += 1
        day_rows = base_rows[i:j]

        for row in day_rows:
            home_history = histories[row.home_team]
            away_history = histories[row.away_team]
            result.append(
                CongestionRow(
                    base=row,
                    home_rest_days=_rest_days(home_history, current),
                    away_rest_days=_rest_days(away_history, current),
                    home_matches_previous_7_days=_recent_count(home_history, current, 7),
                    away_matches_previous_7_days=_recent_count(away_history, current, 7),
                    home_matches_previous_14_days=_recent_count(home_history, current, 14),
                    away_matches_previous_14_days=_recent_count(away_history, current, 14),
                )
            )

        for row in day_rows:
            histories[row.home_team].append(current)
            histories[row.away_team].append(current)
        i = j

    return result


def congestion_vector(row: CongestionRow) -> list[float]:
    return [float(getattr(row, name)) for name in CONGESTION_FEATURE_NAMES]


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def fit_congestion_residual(
    rows: list[CongestionRow],
    *,
    alpha: float = DEFAULT_ALPHA,
) -> CongestionResidualModel:
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    x_raw = np.asarray([congestion_vector(row) for row in rows], dtype=float)
    scaler = StandardScaler().fit(x_raw)
    x = scaler.transform(x_raw)
    base = np.asarray([_market_probs(row.base) for row in rows], dtype=float)
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
        grad_b_h = residual[:, 0].mean()
        grad_b_a = residual[:, 2].mean()
        grad_w_h = (x.T @ residual[:, 0]) / n + alpha * w_h
        grad_w_a = (x.T @ residual[:, 2]) / n + alpha * w_a
        grad = np.concatenate(([grad_b_h, grad_b_a], grad_w_h, grad_w_a))
        return float(nll + penalty), grad

    fitted = minimize(
        lambda t: objective(t)[0],
        np.zeros(2 + 2 * p, dtype=float),
        jac=lambda t: objective(t)[1],
        method="L-BFGS-B",
        options={"maxiter": 3000},
    )
    if not fitted.success:
        raise RuntimeError(f"Congestion residual optimization failed: {fitted.message}")
    b_h, b_a, w_h, w_a = unpack(fitted.x)
    return CongestionResidualModel(scaler, b_h, b_a, w_h.copy(), w_a.copy(), alpha)


def _metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    result = _mean_metrics(items)
    result["top_label_ece"] = _top_label_ece(items)
    return result


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def _economic_metrics(
    predictions: list[tuple[tuple[float, float, float], FeatureRow]],
) -> dict[str, object]:
    bets = wins = 0
    pnl = 0.0
    for probs, row in predictions:
        if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
            continue
        odds = (row.b365_home, row.b365_draw, row.b365_away)
        evs = tuple(probs[index] * odds[index] - 1.0 for index in range(3))
        pick = max(range(3), key=lambda index: evs[index])
        if evs[pick] <= 0:
            continue
        bets += 1
        if RESULTS[pick] == row.result:
            wins += 1
            pnl += odds[pick] - 1.0
        else:
            pnl -= 1.0
    return {
        "rule": "one unit on the single H/D/A outcome with highest model EV only when EV > 0; no edge-size threshold",
        "bets": bets,
        "wins": wins,
        "pnl_units": pnl,
        "roi": pnl / bets if bets else None,
    }


def walk_forward_congestion_residual(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = DEFAULT_ALPHA,
) -> dict[str, object]:
    rows = [
        row
        for row in build_congestion_rows(db_path)
        if row.base.b365_home is not None
        and row.base.b365_draw is not None
        and row.base.b365_away is not None
    ]
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_market: list[tuple[tuple[float, float, float], str]] = []
    all_calibration: list[tuple[tuple[float, float, float], str]] = []
    all_congestion: list[tuple[tuple[float, float, float], str]] = []
    all_congestion_econ: list[tuple[tuple[float, float, float], FeatureRow]] = []
    season_reports: list[dict[str, object]] = []
    latest_weights: dict[str, object] | None = None

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        training_seasons = seasons[:test_index]
        train = [row for row in rows if row.season_start_year in training_seasons]
        test = [row for row in rows if row.season_start_year == test_season]

        calibration = fit_offset_calibration([row.base for row in train])
        congestion = fit_congestion_residual(train, alpha=alpha)

        market_items: list[tuple[tuple[float, float, float], str]] = []
        calibration_items: list[tuple[tuple[float, float, float], str]] = []
        congestion_items: list[tuple[tuple[float, float, float], str]] = []
        congestion_econ: list[tuple[tuple[float, float, float], FeatureRow]] = []

        for row in test:
            market = _market_probs(row.base)
            calibrated = calibration.predict(row.base)
            adjusted = congestion.predict(row)
            market_items.append((market, row.result))
            calibration_items.append((calibrated, row.result))
            congestion_items.append((adjusted, row.result))
            congestion_econ.append((adjusted, row.base))

        all_market.extend(market_items)
        all_calibration.extend(calibration_items)
        all_congestion.extend(congestion_items)
        all_congestion_econ.extend(congestion_econ)

        market_metrics = _metrics(market_items)
        calibration_metrics = _metrics(calibration_items)
        congestion_metrics = _metrics(congestion_items)
        season_reports.append(
            {
                "test_season_start_year": test_season,
                "training_seasons": training_seasons,
                "train_matches": len(train),
                "test_matches": len(test),
                "raw_market": market_metrics,
                "market_offset_calibration": calibration_metrics,
                "market_plus_congestion": {
                    **congestion_metrics,
                    "log_loss_delta_vs_market": _delta(congestion_metrics["log_loss"], market_metrics["log_loss"]),
                    "log_loss_delta_vs_calibration": _delta(congestion_metrics["log_loss"], calibration_metrics["log_loss"]),
                    "brier_delta_vs_market": _delta(congestion_metrics["brier"], market_metrics["brier"]),
                    "brier_delta_vs_calibration": _delta(congestion_metrics["brier"], calibration_metrics["brier"]),
                },
                "economics": _economic_metrics(congestion_econ),
            }
        )

        if test_index == len(seasons) - 1:
            latest_weights = {
                "intercept_h": congestion.intercept_h,
                "intercept_a": congestion.intercept_a,
                "home_vs_draw": {
                    name: float(value)
                    for name, value in zip(CONGESTION_FEATURE_NAMES, congestion.coef_h, strict=True)
                },
                "away_vs_draw": {
                    name: float(value)
                    for name, value in zip(CONGESTION_FEATURE_NAMES, congestion.coef_a, strict=True)
                },
            }

    market_metrics = _metrics(all_market)
    calibration_metrics = _metrics(all_calibration)
    congestion_metrics = _metrics(all_congestion)
    return {
        "status": "historical_walk_forward_audit_only_zero_live_weight",
        "experiment": "fixture_congestion_market_residual_v1",
        "market_source": "B365 pre-closing, de-vigged",
        "feature_names": list(CONGESTION_FEATURE_NAMES),
        "feature_definition": (
            "schedule-only: capped days since previous match plus counts of completed matches in the previous 7 and 14 calendar days; "
            "all fixtures on a date are snapshotted before that date updates schedule history"
        ),
        "split_policy": "walk-forward by season; model fit only on seasons strictly earlier than each test season",
        "hyperparameter_policy": "alpha=0.10 fixed before first OOS audit; no OOS tuning",
        "overall": {
            "raw_market": market_metrics,
            "market_offset_calibration": calibration_metrics,
            "market_plus_congestion": {
                **congestion_metrics,
                "log_loss_delta_vs_market": _delta(congestion_metrics["log_loss"], market_metrics["log_loss"]),
                "log_loss_delta_vs_calibration": _delta(congestion_metrics["log_loss"], calibration_metrics["log_loss"]),
                "brier_delta_vs_market": _delta(congestion_metrics["brier"], market_metrics["brier"]),
                "brier_delta_vs_calibration": _delta(congestion_metrics["brier"], calibration_metrics["brier"]),
            },
        },
        "economics": _economic_metrics(all_congestion_econ),
        "latest_standardized_residual_weights": latest_weights,
        "promotion_rule": (
            "No promotion from this retrospective audit alone. Any advantage must be frozen and survive fresh/prospective testing "
            "before congestion may change a live Football 1 probability or betting view."
        ),
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the leakage-safe fixture-congestion market residual audit.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_congestion_residual(
        args.database,
        min_train_seasons=args.min_train_seasons,
        alpha=args.alpha,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote fixture-congestion residual audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
