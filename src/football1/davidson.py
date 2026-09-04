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
TIME_DECAY_PER_DAY = 0.0015
L2_PENALTY = 0.01


@dataclass(frozen=True)
class MatchRecord:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    market_probs: tuple[float, float, float] | None


@dataclass(frozen=True)
class DavidsonModel:
    teams: tuple[str, ...]
    skill: dict[str, float]
    home_advantage: float
    draw_log_factor: float
    fitted_through: str
    time_decay_per_day: float


@dataclass(frozen=True)
class DavidsonPrediction:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    home_prob: float
    draw_prob: float
    away_prob: float
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
            SELECT match_id, season_start_year, match_date,
                   home_team, away_team, ftr, raw_json
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
            result=str(r[5]),
            market_probs=_market_probs(str(r[6])),
        )
        for r in rows
    ]


def _softmax_rows(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def fit_davidson(
    matches: list[MatchRecord],
    *,
    time_decay_per_day: float = TIME_DECAY_PER_DAY,
    l2_penalty: float = L2_PENALTY,
) -> DavidsonModel:
    """Fit a time-weighted Bradley-Terry-Davidson model.

    The three logits are home skill, away skill and a Davidson tie term at the
    midpoint of the two latent performances. Team skills sum to zero.
    """
    if not matches:
        raise ValueError("Need at least one match")
    if time_decay_per_day < 0.0:
        raise ValueError("time_decay_per_day must be non-negative")
    if l2_penalty < 0.0:
        raise ValueError("l2_penalty must be non-negative")

    teams = tuple(sorted({m.home_team for m in matches} | {m.away_team for m in matches}))
    if len(teams) < 2:
        raise ValueError("Need at least two teams")
    index = {team: i for i, team in enumerate(teams)}
    home_idx = np.asarray([index[m.home_team] for m in matches], dtype=int)
    away_idx = np.asarray([index[m.away_team] for m in matches], dtype=int)
    y = np.asarray([CLASS_ORDER.index(m.result) for m in matches], dtype=int)
    cutoff = max(date.fromisoformat(m.match_date) for m in matches)
    weights = np.asarray(
        [math.exp(-time_decay_per_day * (cutoff - date.fromisoformat(m.match_date)).days) for m in matches],
        dtype=float,
    )
    weight_sum = max(float(weights.sum()), 1e-12)
    n = len(teams)

    # n-1 free skills, home advantage, log Davidson draw factor.
    x0 = np.zeros(n + 1, dtype=float)
    x0[-2] = 0.25
    x0[-1] = -0.45
    bounds = [(None, None)] * (n - 1) + [(-1.5, 1.5), (-3.0, 2.0)]

    def unpack(theta: np.ndarray) -> tuple[np.ndarray, float, float]:
        free = theta[: n - 1]
        skills = np.concatenate((free, [-float(free.sum())]))
        return skills, float(theta[-2]), float(theta[-1])

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        skills, home_adv, draw_log = unpack(theta)
        lh = home_adv + skills[home_idx]
        la = skills[away_idx]
        ld = draw_log + 0.5 * (lh + la)
        logits = np.column_stack((lh, ld, la))
        probs = _softmax_rows(logits)
        chosen = np.clip(probs[np.arange(len(matches)), y], 1e-15, 1.0)
        nll = -float(np.sum(weights * np.log(chosen)) / weight_sum)
        penalty = l2_penalty * float(skills @ skills)

        residual = probs
        residual = residual.copy()
        residual[np.arange(len(matches)), y] -= 1.0
        residual *= (weights / weight_sum)[:, None]

        d_lh = residual[:, 0] + 0.5 * residual[:, 1]
        d_la = residual[:, 2] + 0.5 * residual[:, 1]
        raw_skill_grad = np.zeros(n, dtype=float)
        np.add.at(raw_skill_grad, home_idx, d_lh)
        np.add.at(raw_skill_grad, away_idx, d_la)
        raw_skill_grad += 2.0 * l2_penalty * skills
        free_grad = raw_skill_grad[:-1] - raw_skill_grad[-1]
        home_grad = float(d_lh.sum())
        draw_grad = float(residual[:, 1].sum())
        grad = np.concatenate((free_grad, [home_grad, draw_grad]))
        return nll + penalty, grad

    result = minimize(
        lambda theta: objective(theta)[0],
        x0,
        jac=lambda theta: objective(theta)[1],
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 2000, "ftol": 1e-11},
    )
    if not result.success:
        raise RuntimeError(f"Davidson optimization failed: {result.message}")
    skills, home_adv, draw_log = unpack(result.x)
    return DavidsonModel(
        teams=teams,
        skill={team: float(value) for team, value in zip(teams, skills)},
        home_advantage=home_adv,
        draw_log_factor=draw_log,
        fitted_through=cutoff.isoformat(),
        time_decay_per_day=time_decay_per_day,
    )


def predict_probs(model: DavidsonModel, home_team: str, away_team: str) -> tuple[float, float, float]:
    # Unseen/promoted clubs are neutral in EPL-only v1.
    home_skill = model.skill.get(home_team, 0.0)
    away_skill = model.skill.get(away_team, 0.0)
    lh = model.home_advantage + home_skill
    la = away_skill
    ld = model.draw_log_factor + 0.5 * (lh + la)
    x = np.asarray([[lh, ld, la]], dtype=float)
    p = _softmax_rows(x)[0]
    return (float(p[0]), float(p[1]), float(p[2]))


def predict_match(model: DavidsonModel, match: MatchRecord) -> DavidsonPrediction:
    p = predict_probs(model, match.home_team, match.away_team)
    return DavidsonPrediction(
        match_id=match.match_id,
        season_start_year=match.season_start_year,
        match_date=match.match_date,
        home_team=match.home_team,
        away_team=match.away_team,
        result=match.result,
        home_prob=p[0],
        draw_prob=p[1],
        away_prob=p[2],
        market_probs=match.market_probs,
    )


def _top_label_ece(items: list[tuple[tuple[float, float, float], str]], bins: int = 10) -> float:
    if not items:
        return 0.0
    ece = 0.0
    total = len(items)
    for k in range(bins):
        lo, hi = k / bins, (k + 1) / bins
        bucket: list[tuple[float, bool]] = []
        for probs, result in items:
            idx = max(range(3), key=lambda i: probs[i])
            conf = probs[idx]
            if (lo <= conf < hi) or (k == bins - 1 and conf == hi):
                bucket.append((conf, CLASS_ORDER[idx] == result))
        if bucket:
            mean_conf = sum(x[0] for x in bucket) / len(bucket)
            accuracy = sum(1.0 for x in bucket if x[1]) / len(bucket)
            ece += len(bucket) / total * abs(accuracy - mean_conf)
    return ece


def _metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    if not items:
        return {"matches": 0, "log_loss": None, "brier": None, "accuracy": None, "top_label_ece": None}
    scores = [score_probabilities(p, result) for p, result in items]
    n = len(scores)
    return {
        "matches": n,
        "log_loss": sum(s.log_loss for s in scores) / n,
        "brier": sum(s.brier for s in scores) / n,
        "accuracy": sum(s.correct for s in scores) / n,
        "top_label_ece": _top_label_ece(items),
    }


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def walk_forward_davidson(
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
    reports: list[dict[str, object]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train = [m for m in matches if m.season_start_year in seasons[:test_index]]
        test = [m for m in matches if m.season_start_year == test_season]
        model = fit_davidson(train, time_decay_per_day=time_decay_per_day)
        preds = [predict_match(model, m) for m in test]
        model_items = [((p.home_prob, p.draw_prob, p.away_prob), p.result) for p in preds]
        paired_model = [
            ((p.home_prob, p.draw_prob, p.away_prob), p.result)
            for p in preds if p.market_probs is not None
        ]
        paired_market = [(p.market_probs, p.result) for p in preds if p.market_probs is not None]
        paired_market = [(p, r) for p, r in paired_market if p is not None]
        all_model.extend(model_items)
        all_model_paired.extend(paired_model)
        all_market.extend(paired_market)  # type: ignore[arg-type]
        mm = _metrics(model_items)
        pm = _metrics(paired_model)
        mk = _metrics(paired_market)  # type: ignore[arg-type]
        reports.append({
            "test_season_start_year": test_season,
            "train_matches": len(train),
            "test_matches": len(test),
            "home_advantage": model.home_advantage,
            "draw_factor": math.exp(model.draw_log_factor),
            "davidson": mm,
            "paired_b365_pre_closing": {
                "matches": pm["matches"],
                "model_log_loss": pm["log_loss"],
                "market_log_loss": mk["log_loss"],
                "log_loss_delta_model_minus_market": _delta(pm["log_loss"], mk["log_loss"]),
                "model_brier": pm["brier"],
                "market_brier": mk["brier"],
                "brier_delta_model_minus_market": _delta(pm["brier"], mk["brier"]),
            },
        })

    full_model = fit_davidson(matches, time_decay_per_day=time_decay_per_day)
    overall = _metrics(all_model)
    paired = _metrics(all_model_paired)
    market = _metrics(all_market)
    return {
        "model": "time_weighted_davidson_v1",
        "model_policy": "Bradley-Terry-Davidson paired comparison with an explicit draw term and home advantage",
        "hyperparameter_policy": "time decay and L2 fixed before OOS evaluation; no OOS tuning",
        "evaluation_policy": "strict walk-forward by season; each held-out season is fit only on earlier seasons",
        "promotion_policy": "unseen/promoted teams enter at neutral strength in EPL-only v1",
        "parameters": {
            "time_decay_per_day": time_decay_per_day,
            "l2_penalty": L2_PENALTY,
        },
        "overall_model": overall,
        "paired_overall": {
            "matches": paired["matches"],
            "model_log_loss": paired["log_loss"],
            "market_log_loss": market["log_loss"],
            "log_loss_delta_model_minus_market": _delta(paired["log_loss"], market["log_loss"]),
            "model_brier": paired["brier"],
            "market_brier": market["brier"],
            "brier_delta_model_minus_market": _delta(paired["brier"], market["brier"]),
        },
        "current_fit": {
            "fitted_through": full_model.fitted_through,
            "home_advantage": full_model.home_advantage,
            "draw_factor": math.exp(full_model.draw_log_factor),
            "strengths": [
                {"team": team, "strength": strength}
                for team, strength in sorted(full_model.skill.items(), key=lambda x: (-x[1], x[0]))
            ],
        },
        "seasons": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Time-weighted Davidson EPL three-outcome audit.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_davidson(args.database, min_train_seasons=args.min_train_seasons)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote Davidson report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
