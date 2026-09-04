from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from football1.market_baseline import devig_decimal_odds, score_probabilities


CLASS_ORDER = ("H", "D", "A")
TIME_DECAY_PER_DAY = 0.0020
L2_PENALTY = 0.0025
RHO_BOUND = 0.20
MAX_SCORE = 10


@dataclass(frozen=True)
class MatchRecord:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    result: str
    market_probs: tuple[float, float, float] | None


@dataclass(frozen=True)
class DixonColesModel:
    teams: tuple[str, ...]
    attack: dict[str, float]
    defence: dict[str, float]
    home_advantage: float
    rho: float
    fitted_through: str
    time_decay_per_day: float


@dataclass(frozen=True)
class DixonColesPrediction:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    expected_home_goals: float
    expected_away_goals: float
    rho: float
    home_prob: float
    draw_prob: float
    away_prob: float
    top_score_home: int
    top_score_away: int
    top_score_prob: float
    market_probs: tuple[float, float, float] | None


def _market_probs(raw_json: str) -> tuple[float, float, float] | None:
    raw = json.loads(raw_json)
    try:
        odds = tuple(float(str(raw.get(k, "")).strip()) for k in ("B365H", "B365D", "B365A"))
    except (TypeError, ValueError):
        return None
    if any((not math.isfinite(x)) or x <= 1.0 for x in odds):
        return None
    return devig_decimal_odds(odds)[0]  # type: ignore[arg-type]


def load_matches(db_path: Path) -> list[MatchRecord]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT match_id, season_start_year, match_date, home_team, away_team,
                   fthg, ftag, ftr, raw_json
            FROM matches
            ORDER BY match_date, match_id
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        MatchRecord(
            match_id=str(r[0]),
            season_start_year=int(r[1]),
            match_date=str(r[2]),
            home_team=str(r[3]),
            away_team=str(r[4]),
            home_goals=int(r[5]),
            away_goals=int(r[6]),
            result=str(r[7]),
            market_probs=_market_probs(str(r[8])),
        )
        for r in rows
    ]


def dc_tau(home_goals: int, away_goals: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles low-score dependence correction."""
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lam * mu * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lam * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + mu * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def _poisson_logpmf(goals: int, lam: float) -> float:
    return goals * math.log(lam) - lam - math.lgamma(goals + 1.0)


def _poisson_pmf(lam: float, max_score: int) -> list[float]:
    result = [math.exp(-lam)]
    for goals in range(1, max_score + 1):
        result.append(result[-1] * lam / goals)
    return result


def _unpack(theta: np.ndarray, teams: tuple[str, ...]) -> tuple[dict[str, float], dict[str, float], float, float]:
    n = len(teams)
    # The final attack parameter is derived so attacks sum to zero.
    free_attack = theta[: n - 1]
    attacks = np.concatenate((free_attack, [-float(np.sum(free_attack))]))
    defences = theta[n - 1 : n - 1 + n]
    home_advantage = float(theta[-2])
    rho = float(theta[-1])
    return (
        {team: float(value) for team, value in zip(teams, attacks)},
        {team: float(value) for team, value in zip(teams, defences)},
        home_advantage,
        rho,
    )


def fit_dixon_coles(
    matches: list[MatchRecord],
    *,
    time_decay_per_day: float = TIME_DECAY_PER_DAY,
    l2_penalty: float = L2_PENALTY,
) -> DixonColesModel:
    if not matches:
        raise ValueError("Need at least one match to fit Dixon-Coles")
    if time_decay_per_day < 0:
        raise ValueError("time_decay_per_day must be non-negative")
    teams = tuple(sorted({m.home_team for m in matches} | {m.away_team for m in matches}))
    if len(teams) < 2:
        raise ValueError("Need at least two teams")
    team_to_index = {team: i for i, team in enumerate(teams)}
    cutoff = max(date.fromisoformat(m.match_date) for m in matches)
    weights = np.asarray(
        [math.exp(-time_decay_per_day * (cutoff - date.fromisoformat(m.match_date)).days) for m in matches],
        dtype=float,
    )

    n = len(teams)
    # attacks n-1, defences n, home advantage, rho
    x0 = np.zeros((n - 1) + n + 2, dtype=float)
    x0[-2] = math.log(1.15)
    x0[-1] = -0.05
    bounds = [(None, None)] * (len(x0) - 2) + [(-1.0, 1.0), (-RHO_BOUND, RHO_BOUND)]

    def objective(theta: np.ndarray) -> float:
        attack_free = theta[: n - 1]
        attacks = np.concatenate((attack_free, [-float(np.sum(attack_free))]))
        defences = theta[n - 1 : n - 1 + n]
        home_adv = float(theta[-2])
        rho = float(theta[-1])
        loss = 0.0
        for weight, m in zip(weights, matches):
            hi = team_to_index[m.home_team]
            ai = team_to_index[m.away_team]
            lam = math.exp(home_adv + attacks[hi] + defences[ai])
            mu = math.exp(attacks[ai] + defences[hi])
            tau = dc_tau(m.home_goals, m.away_goals, lam, mu, rho)
            if tau <= 1e-12 or not math.isfinite(tau):
                return 1e12
            ll = _poisson_logpmf(m.home_goals, lam) + _poisson_logpmf(m.away_goals, mu) + math.log(tau)
            loss -= float(weight) * ll
        penalty = l2_penalty * float(np.sum(attack_free**2) + np.sum(defences**2))
        return loss / max(float(np.sum(weights)), 1e-12) + penalty

    result = minimize(
        objective,
        x0,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 2500, "ftol": 1e-10},
    )
    if not result.success:
        raise RuntimeError(f"Dixon-Coles optimization failed: {result.message}")
    attack, defence, home_advantage, rho = _unpack(result.x, teams)
    return DixonColesModel(
        teams=teams,
        attack=attack,
        defence=defence,
        home_advantage=home_advantage,
        rho=rho,
        fitted_through=cutoff.isoformat(),
        time_decay_per_day=time_decay_per_day,
    )


def expected_goals(model: DixonColesModel, home_team: str, away_team: str) -> tuple[float, float]:
    # Unseen/promoted clubs enter at neutral league-average attack/defence in v1.
    home_attack = model.attack.get(home_team, 0.0)
    away_attack = model.attack.get(away_team, 0.0)
    home_defence = model.defence.get(home_team, 0.0)
    away_defence = model.defence.get(away_team, 0.0)
    return (
        math.exp(model.home_advantage + home_attack + away_defence),
        math.exp(away_attack + home_defence),
    )


def scoreline_distribution(
    model: DixonColesModel,
    home_team: str,
    away_team: str,
    *,
    max_score: int = MAX_SCORE,
) -> tuple[tuple[float, float, float], tuple[int, int, float], tuple[float, float]]:
    lam, mu = expected_goals(model, home_team, away_team)
    hp = _poisson_pmf(lam, max_score)
    ap = _poisson_pmf(mu, max_score)
    cells: list[tuple[int, int, float]] = []
    total = 0.0
    for h, p_h in enumerate(hp):
        for a, p_a in enumerate(ap):
            p = p_h * p_a * dc_tau(h, a, lam, mu, model.rho)
            if p < 0 or not math.isfinite(p):
                raise ValueError("Invalid Dixon-Coles score probability")
            cells.append((h, a, p))
            total += p
    if total <= 0:
        raise ValueError("Dixon-Coles score grid has no mass")

    home = draw = away = 0.0
    best = (0, 0, -1.0)
    for h, a, raw_p in cells:
        p = raw_p / total
        if p > best[2]:
            best = (h, a, p)
        if h > a:
            home += p
        elif h == a:
            draw += p
        else:
            away += p
    norm = home + draw + away
    return (home / norm, draw / norm, away / norm), best, (lam, mu)


def predict_match(model: DixonColesModel, match: MatchRecord) -> DixonColesPrediction:
    probs, modal, lambdas = scoreline_distribution(model, match.home_team, match.away_team)
    return DixonColesPrediction(
        match_id=match.match_id,
        season_start_year=match.season_start_year,
        match_date=match.match_date,
        home_team=match.home_team,
        away_team=match.away_team,
        result=match.result,
        expected_home_goals=lambdas[0],
        expected_away_goals=lambdas[1],
        rho=model.rho,
        home_prob=probs[0],
        draw_prob=probs[1],
        away_prob=probs[2],
        top_score_home=modal[0],
        top_score_away=modal[1],
        top_score_prob=modal[2],
        market_probs=match.market_probs,
    )


def _top_label_ece(items: list[tuple[tuple[float, float, float], str]], bins: int = 10) -> float:
    if not items:
        return 0.0
    total = len(items)
    ece = 0.0
    for k in range(bins):
        lo, hi = k / bins, (k + 1) / bins
        bucket: list[tuple[float, bool]] = []
        for probs, result in items:
            idx = max(range(3), key=lambda i: probs[i])
            confidence = probs[idx]
            if (lo <= confidence < hi) or (k == bins - 1 and confidence == hi):
                bucket.append((confidence, CLASS_ORDER[idx] == result))
        if bucket:
            mean_conf = sum(x[0] for x in bucket) / len(bucket)
            accuracy = sum(1.0 for x in bucket if x[1]) / len(bucket)
            ece += (len(bucket) / total) * abs(accuracy - mean_conf)
    return ece


def _metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    if not items:
        return {"matches": 0, "log_loss": None, "brier": None, "accuracy": None, "top_label_ece": None}
    scores = [score_probabilities(probs, result) for probs, result in items]
    n = len(scores)
    return {
        "matches": n,
        "log_loss": sum(x.log_loss for x in scores) / n,
        "brier": sum(x.brier for x in scores) / n,
        "accuracy": sum(x.correct for x in scores) / n,
        "top_label_ece": _top_label_ece(items),
    }


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def walk_forward_dixon_coles(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    time_decay_per_day: float = TIME_DECAY_PER_DAY,
) -> dict[str, object]:
    matches = load_matches(db_path)
    seasons = sorted({m.season_start_year for m in matches})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_model: list[tuple[tuple[float, float, float], str]] = []
    all_model_paired: list[tuple[tuple[float, float, float], str]] = []
    all_market: list[tuple[tuple[float, float, float], str]] = []
    season_reports: list[dict[str, object]] = []
    latest_predictions: list[DixonColesPrediction] = []
    latest_model: DixonColesModel | None = None

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train_seasons = set(seasons[:test_index])
        train = [m for m in matches if m.season_start_year in train_seasons]
        test = [m for m in matches if m.season_start_year == test_season]
        model = fit_dixon_coles(train, time_decay_per_day=time_decay_per_day)
        preds = [predict_match(model, m) for m in test]
        model_items = [((p.home_prob, p.draw_prob, p.away_prob), p.result) for p in preds]
        paired_model = [
            ((p.home_prob, p.draw_prob, p.away_prob), p.result)
            for p in preds
            if p.market_probs is not None
        ]
        paired_market = [(p.market_probs, p.result) for p in preds if p.market_probs is not None]
        paired_market = [(x, y) for x, y in paired_market if x is not None]
        all_model.extend(model_items)
        all_model_paired.extend(paired_model)
        all_market.extend(paired_market)  # type: ignore[arg-type]
        mm = _metrics(model_items)
        pm = _metrics(paired_model)
        mk = _metrics(paired_market)  # type: ignore[arg-type]
        season_reports.append(
            {
                "test_season_start_year": test_season,
                "train_matches": len(train),
                "test_matches": len(test),
                "rho": model.rho,
                "home_advantage_log_rate": model.home_advantage,
                "dixon_coles": mm,
                "paired_b365_pre_closing": {
                    "matches": pm["matches"],
                    "model_log_loss": pm["log_loss"],
                    "market_log_loss": mk["log_loss"],
                    "log_loss_delta_model_minus_market": _delta(pm["log_loss"], mk["log_loss"]),
                    "model_brier": pm["brier"],
                    "market_brier": mk["brier"],
                    "brier_delta_model_minus_market": _delta(pm["brier"], mk["brier"]),
                },
            }
        )
        latest_predictions = preds[-20:]
        latest_model = model

    overall = _metrics(all_model)
    paired_model_m = _metrics(all_model_paired)
    market_m = _metrics(all_market)
    return {
        "model": "dixon_coles_v1",
        "parameters": {
            "time_decay_per_day": time_decay_per_day,
            "time_decay_half_life_days": math.log(2.0) / time_decay_per_day if time_decay_per_day > 0 else None,
            "l2_penalty": L2_PENALTY,
            "rho_bound": RHO_BOUND,
            "max_score": MAX_SCORE,
        },
        "hyperparameter_policy": "v1 decay, regularization, rho bound and score grid fixed before OOS evaluation; no OOS tuning",
        "fit_policy": "classic time-weighted Dixon-Coles attack/defence likelihood with low-score dependence correction; model refit at the start of each held-out season using earlier EPL seasons only",
        "promotion_policy": "teams unseen in the training history enter at neutral attack/defence; no invented lower-league strength",
        "evaluation_policy": "strict walk-forward by season; no held-out-season result is used to refit that season's model",
        "overall_model": overall,
        "paired_overall": {
            "matches": paired_model_m["matches"],
            "model_log_loss": paired_model_m["log_loss"],
            "market_log_loss": market_m["log_loss"],
            "log_loss_delta_model_minus_market": _delta(paired_model_m["log_loss"], market_m["log_loss"]),
            "model_brier": paired_model_m["brier"],
            "market_brier": market_m["brier"],
            "brier_delta_model_minus_market": _delta(paired_model_m["brier"], market_m["brier"]),
        },
        "latest_fit": {
            "fitted_through": latest_model.fitted_through if latest_model else None,
            "rho": latest_model.rho if latest_model else None,
            "home_advantage_log_rate": latest_model.home_advantage if latest_model else None,
        },
        "latest_predictions": [
            {
                "match_id": p.match_id,
                "date": p.match_date,
                "home_team": p.home_team,
                "away_team": p.away_team,
                "expected_home_goals": p.expected_home_goals,
                "expected_away_goals": p.expected_away_goals,
                "home_prob": p.home_prob,
                "draw_prob": p.draw_prob,
                "away_prob": p.away_prob,
                "modal_score": f"{p.top_score_home}-{p.top_score_away}",
                "modal_score_prob": p.top_score_prob,
            }
            for p in latest_predictions
        ],
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Leakage-safe EPL Dixon-Coles score model audit.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--time-decay-per-day", type=float, default=TIME_DECAY_PER_DAY)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_dixon_coles(
        args.database,
        min_train_seasons=args.min_train_seasons,
        time_decay_per_day=args.time_decay_per_day,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote Dixon-Coles report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
