from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from scipy.optimize import minimize_scalar
from scipy.special import gammaln, logsumexp

from football1.scoreline import ScorelineRow, _metrics, build_scoreline_history


TIME_DECAY_PER_DAY = 0.0020
MAX_SCORE = 12
COMMON_FRACTION_MAX = 0.75
FRAILTY_K_MIN = 0.50
FRAILTY_K_MAX = 200.0


@dataclass(frozen=True)
class DependenceFit:
    common_fraction: float
    frailty_k: float
    fitted_through: str
    train_matches: int


@dataclass(frozen=True)
class CorrelatedPrediction:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    expected_home_goals: float
    expected_away_goals: float
    independent_probs: tuple[float, float, float]
    bivariate_probs: tuple[float, float, float]
    frailty_probs: tuple[float, float, float]
    common_fraction: float
    frailty_k: float
    market_probs: tuple[float, float, float] | None


def load_actual_scores(db_path: Path) -> dict[str, tuple[int, int]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT match_id, fthg, ftag FROM matches").fetchall()
    finally:
        conn.close()
    return {str(match_id): (int(home), int(away)) for match_id, home, away in rows}


def _safe_log_power(rate: float, count: int) -> float | None:
    if count == 0:
        return 0.0
    if rate <= 0.0:
        return None
    return count * math.log(rate)


def bivariate_poisson_logpmf(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    common_fraction: float,
) -> float:
    """Joint PMF with a shared Poisson component while preserving marginal means."""
    if not (0.0 <= common_fraction < 1.0):
        raise ValueError("common_fraction must be in [0, 1)")
    shared = common_fraction * min(lambda_home, lambda_away)
    home_only = lambda_home - shared
    away_only = lambda_away - shared
    terms: list[float] = []
    for shared_goals in range(min(home_goals, away_goals) + 1):
        h = home_goals - shared_goals
        a = away_goals - shared_goals
        pieces = [
            _safe_log_power(home_only, h),
            _safe_log_power(away_only, a),
            _safe_log_power(shared, shared_goals),
        ]
        if any(piece is None for piece in pieces):
            continue
        terms.append(
            float(pieces[0])
            + float(pieces[1])
            + float(pieces[2])
            - gammaln(h + 1.0)
            - gammaln(a + 1.0)
            - gammaln(shared_goals + 1.0)
        )
    if not terms:
        return float("-inf")
    return -(home_only + away_only + shared) + float(logsumexp(terms))


def gamma_frailty_logpmf(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    k: float,
) -> float:
    """Shared-Gamma tempo/frailty model.

    Conditional on latent match tempo Z, both goal counts are independent
    Poisson(Z * lambda). Z ~ Gamma(k, rate=k), so E[Z]=1. Smaller k means
    greater common match-tempo volatility; k -> infinity approaches independent
    Poisson.
    """
    if k <= 0.0:
        raise ValueError("k must be positive")
    denominator = k + lambda_home + lambda_away
    return float(
        gammaln(k + home_goals + away_goals)
        - gammaln(k)
        - gammaln(home_goals + 1.0)
        - gammaln(away_goals + 1.0)
        + k * math.log(k / denominator)
        + home_goals * math.log(lambda_home / denominator)
        + away_goals * math.log(lambda_away / denominator)
    )


def _joint_to_1x2(
    logpmf,
    lambda_home: float,
    lambda_away: float,
    parameter: float,
    *,
    max_score: int = MAX_SCORE,
) -> tuple[float, float, float]:
    home = draw = away = total = 0.0
    for h in range(max_score + 1):
        for a in range(max_score + 1):
            p = math.exp(logpmf(h, a, lambda_home, lambda_away, parameter))
            total += p
            if h > a:
                home += p
            elif h == a:
                draw += p
            else:
                away += p
    if total <= 0.0 or not math.isfinite(total):
        raise ValueError("Correlated score grid has no finite probability mass")
    return home / total, draw / total, away / total


def bivariate_probabilities(
    lambda_home: float,
    lambda_away: float,
    common_fraction: float,
) -> tuple[float, float, float]:
    return _joint_to_1x2(
        bivariate_poisson_logpmf,
        lambda_home,
        lambda_away,
        common_fraction,
    )


def frailty_probabilities(
    lambda_home: float,
    lambda_away: float,
    k: float,
) -> tuple[float, float, float]:
    return _joint_to_1x2(gamma_frailty_logpmf, lambda_home, lambda_away, k)


def _time_weights(rows: list[ScorelineRow]) -> tuple[str, list[float]]:
    cutoff = max(date.fromisoformat(row.match_date) for row in rows)
    weights = [
        math.exp(-TIME_DECAY_PER_DAY * (cutoff - date.fromisoformat(row.match_date)).days)
        for row in rows
    ]
    return cutoff.isoformat(), weights


def fit_dependence(
    rows: list[ScorelineRow],
    actual_scores: dict[str, tuple[int, int]],
) -> DependenceFit:
    if not rows:
        raise ValueError("Need training rows")
    fitted_through, weights = _time_weights(rows)

    def common_objective(common_fraction: float) -> float:
        weighted = 0.0
        total_weight = 0.0
        for row, weight in zip(rows, weights):
            home_goals, away_goals = actual_scores[row.match_id]
            ll = bivariate_poisson_logpmf(
                home_goals,
                away_goals,
                row.expected_home_goals,
                row.expected_away_goals,
                common_fraction,
            )
            weighted -= weight * ll
            total_weight += weight
        return weighted / total_weight

    common_result = minimize_scalar(
        common_objective,
        bounds=(0.0, COMMON_FRACTION_MAX),
        method="bounded",
        options={"xatol": 1e-6},
    )
    if not common_result.success:
        raise RuntimeError(f"Bivariate-Poisson fit failed: {common_result.message}")

    log_k_min = math.log(FRAILTY_K_MIN)
    log_k_max = math.log(FRAILTY_K_MAX)

    def frailty_objective(log_k: float) -> float:
        k = math.exp(log_k)
        weighted = 0.0
        total_weight = 0.0
        for row, weight in zip(rows, weights):
            home_goals, away_goals = actual_scores[row.match_id]
            ll = gamma_frailty_logpmf(
                home_goals,
                away_goals,
                row.expected_home_goals,
                row.expected_away_goals,
                k,
            )
            weighted -= weight * ll
            total_weight += weight
        return weighted / total_weight

    frailty_result = minimize_scalar(
        frailty_objective,
        bounds=(log_k_min, log_k_max),
        method="bounded",
        options={"xatol": 1e-6},
    )
    if not frailty_result.success:
        raise RuntimeError(f"Gamma-frailty fit failed: {frailty_result.message}")

    return DependenceFit(
        common_fraction=float(common_result.x),
        frailty_k=float(math.exp(frailty_result.x)),
        fitted_through=fitted_through,
        train_matches=len(rows),
    )


def predict_row(row: ScorelineRow, fit: DependenceFit) -> CorrelatedPrediction:
    bivariate = bivariate_probabilities(
        row.expected_home_goals,
        row.expected_away_goals,
        fit.common_fraction,
    )
    frailty = frailty_probabilities(
        row.expected_home_goals,
        row.expected_away_goals,
        fit.frailty_k,
    )
    return CorrelatedPrediction(
        match_id=row.match_id,
        season_start_year=row.season_start_year,
        match_date=row.match_date,
        home_team=row.home_team,
        away_team=row.away_team,
        result=row.result,
        expected_home_goals=row.expected_home_goals,
        expected_away_goals=row.expected_away_goals,
        independent_probs=(row.home_prob, row.draw_prob, row.away_prob),
        bivariate_probs=bivariate,
        frailty_probs=frailty,
        common_fraction=fit.common_fraction,
        frailty_k=fit.frailty_k,
        market_probs=row.market_probs,
    )


def season_start_prediction_map(db_path: Path) -> dict[str, CorrelatedPrediction]:
    rows = build_scoreline_history(db_path)
    actual = load_actual_scores(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    result: dict[str, CorrelatedPrediction] = {}
    for index, season in enumerate(seasons):
        if index == 0:
            continue
        train = [row for row in rows if row.season_start_year in seasons[:index]]
        fit = fit_dependence(train, actual)
        for row in rows:
            if row.season_start_year == season:
                result[row.match_id] = predict_row(row, fit)
    return result


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def walk_forward_correlated_score(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
) -> dict[str, object]:
    rows = build_scoreline_history(db_path)
    actual = load_actual_scores(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_independent: list[tuple[tuple[float, float, float], str]] = []
    all_bivariate: list[tuple[tuple[float, float, float], str]] = []
    all_frailty: list[tuple[tuple[float, float, float], str]] = []
    all_market: list[tuple[tuple[float, float, float], str]] = []
    reports: list[dict[str, object]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train = [row for row in rows if row.season_start_year in seasons[:test_index]]
        test = [row for row in rows if row.season_start_year == test_season]
        fit = fit_dependence(train, actual)
        preds = [predict_row(row, fit) for row in test]

        independent = [(p.independent_probs, p.result) for p in preds]
        bivariate = [(p.bivariate_probs, p.result) for p in preds]
        frailty = [(p.frailty_probs, p.result) for p in preds]
        market = [(p.market_probs, p.result) for p in preds if p.market_probs is not None]
        market = [(p, result) for p, result in market if p is not None]

        all_independent.extend(independent)
        all_bivariate.extend(bivariate)
        all_frailty.extend(frailty)
        all_market.extend(market)  # type: ignore[arg-type]

        independent_m = _metrics(independent)
        bivariate_m = _metrics(bivariate)
        frailty_m = _metrics(frailty)
        market_m = _metrics(market)  # type: ignore[arg-type]
        reports.append(
            {
                "test_season_start_year": test_season,
                "train_matches": len(train),
                "test_matches": len(test),
                "fit": {
                    "common_fraction": fit.common_fraction,
                    "frailty_k": fit.frailty_k,
                    "frailty_tempo_cv": 1.0 / math.sqrt(fit.frailty_k),
                    "fitted_through": fit.fitted_through,
                },
                "independent_poisson": independent_m,
                "bivariate_poisson": {
                    **bivariate_m,
                    "log_loss_delta_vs_independent": _delta(
                        bivariate_m["log_loss"], independent_m["log_loss"]
                    ),
                },
                "gamma_frailty": {
                    **frailty_m,
                    "log_loss_delta_vs_independent": _delta(
                        frailty_m["log_loss"], independent_m["log_loss"]
                    ),
                },
                "market": market_m,
            }
        )

    independent = _metrics(all_independent)
    bivariate = _metrics(all_bivariate)
    frailty = _metrics(all_frailty)
    market = _metrics(all_market)
    current_fit = fit_dependence(rows, actual)
    return {
        "experiment": "correlated_score_models_v1",
        "status": "shadow_context_only",
        "base_goal_model": "existing leakage-safe rolling home/away independent-Poisson expected goals",
        "hyperparameter_policy": (
            "time decay 0.002/day, common-fraction bound [0,0.75], frailty k bound "
            "[0.5,200], fixed before OOS; dependence parameters fit only on seasons before each held-out season"
        ),
        "bivariate_interpretation": (
            "A shared Poisson goal component represents common match shocks and induces positive score covariance while preserving the base marginal means."
        ),
        "frailty_interpretation": (
            "A shared Gamma match-tempo multiplier comes from random-effects/frailty modelling; smaller k means greater common tempo volatility and overdispersion."
        ),
        "overall": {
            "independent_poisson": independent,
            "bivariate_poisson": {
                **bivariate,
                "log_loss_delta_vs_independent": _delta(
                    bivariate["log_loss"], independent["log_loss"]
                ),
                "brier_delta_vs_independent": _delta(
                    bivariate["brier"], independent["brier"]
                ),
            },
            "gamma_frailty": {
                **frailty,
                "log_loss_delta_vs_independent": _delta(
                    frailty["log_loss"], independent["log_loss"]
                ),
                "brier_delta_vs_independent": _delta(
                    frailty["brier"], independent["brier"]
                ),
            },
            "market": market,
        },
        "current_fit": {
            "common_fraction": current_fit.common_fraction,
            "frailty_k": current_fit.frailty_k,
            "frailty_tempo_cv": 1.0 / math.sqrt(current_fit.frailty_k),
            "fitted_through": current_fit.fitted_through,
            "train_matches": current_fit.train_matches,
        },
        "seasons": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit correlated score models on top of Football 1's leakage-safe Poisson expected goals."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/processed/football1.sqlite"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_correlated_score(
        args.database,
        min_train_seasons=args.min_train_seasons,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote correlated-score report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
