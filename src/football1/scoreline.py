from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from football1.market_baseline import devig_decimal_odds, score_probabilities


TEAM_ROLE_WINDOW = 20
LEAGUE_WINDOW = 760
PRIOR_WEIGHT = 5.0
FALLBACK_HOME_GOALS = 1.50
FALLBACK_AWAY_GOALS = 1.20
MIN_LAMBDA = 0.15
MAX_LAMBDA = 5.00
MAX_SCORE = 10
CLASS_ORDER = ("H", "D", "A")


@dataclass(frozen=True)
class ScoreGame:
    goals_for: float
    goals_against: float


@dataclass
class TeamRoleState:
    home_games: deque[ScoreGame]
    away_games: deque[ScoreGame]

    @classmethod
    def empty(cls) -> "TeamRoleState":
        return cls(
            home_games=deque(maxlen=TEAM_ROLE_WINDOW),
            away_games=deque(maxlen=TEAM_ROLE_WINDOW),
        )


@dataclass(frozen=True)
class ScorelineRow:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    expected_home_goals: float
    expected_away_goals: float
    home_prob: float
    draw_prob: float
    away_prob: float
    top_score_home: int
    top_score_away: int
    top_score_prob: float
    market_probs: tuple[float, float, float] | None


def _mean(values: deque[float], fallback: float) -> float:
    if not values:
        return fallback
    return sum(values) / len(values)


def _smoothed_mean(values: list[float], prior_mean: float) -> float:
    return (sum(values) + PRIOR_WEIGHT * prior_mean) / (len(values) + PRIOR_WEIGHT)


def expected_goals(
    *,
    home_history: deque[ScoreGame],
    away_history: deque[ScoreGame],
    league_home_goals: float,
    league_away_goals: float,
) -> tuple[float, float]:
    """Estimate goals from venue-specific attack and defence strengths."""
    home_gf = _smoothed_mean([game.goals_for for game in home_history], league_home_goals)
    home_ga = _smoothed_mean([game.goals_against for game in home_history], league_away_goals)
    away_gf = _smoothed_mean([game.goals_for for game in away_history], league_away_goals)
    away_ga = _smoothed_mean([game.goals_against for game in away_history], league_home_goals)

    safe_home_base = max(league_home_goals, 0.25)
    safe_away_base = max(league_away_goals, 0.25)

    home_attack = home_gf / safe_home_base
    away_defence = away_ga / safe_home_base
    away_attack = away_gf / safe_away_base
    home_defence = home_ga / safe_away_base

    lambda_home = league_home_goals * home_attack * away_defence
    lambda_away = league_away_goals * away_attack * home_defence
    lambda_home = min(MAX_LAMBDA, max(MIN_LAMBDA, lambda_home))
    lambda_away = min(MAX_LAMBDA, max(MIN_LAMBDA, lambda_away))
    return lambda_home, lambda_away


def _poisson_pmf(lam: float, max_score: int = MAX_SCORE) -> list[float]:
    probs = [math.exp(-lam)]
    for goals in range(1, max_score + 1):
        probs.append(probs[-1] * lam / goals)
    return probs


def scoreline_distribution(
    lambda_home: float,
    lambda_away: float,
    *,
    max_score: int = MAX_SCORE,
) -> tuple[tuple[float, float, float], tuple[int, int, float]]:
    """Return H/D/A and modal score from an independent-Poisson score grid."""
    home_pmf = _poisson_pmf(lambda_home, max_score)
    away_pmf = _poisson_pmf(lambda_away, max_score)
    total_mass = sum(home_pmf) * sum(away_pmf)
    if total_mass <= 0:
        raise ValueError("Poisson score grid has no probability mass")

    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    best_home = 0
    best_away = 0
    best_prob = -1.0

    for home_goals, hp in enumerate(home_pmf):
        for away_goals, ap in enumerate(away_pmf):
            probability = (hp * ap) / total_mass
            if probability > best_prob:
                best_prob = probability
                best_home = home_goals
                best_away = away_goals
            if home_goals > away_goals:
                home_win += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                away_win += probability

    norm = home_win + draw + away_win
    probs = (home_win / norm, draw / norm, away_win / norm)
    return probs, (best_home, best_away, best_prob)


def _parse_market_probs(raw_json: str) -> tuple[float, float, float] | None:
    raw = json.loads(raw_json)
    try:
        odds = tuple(float(str(raw.get(name, "")).strip()) for name in ("B365H", "B365D", "B365A"))
    except (TypeError, ValueError):
        return None
    if any((not math.isfinite(value)) or value <= 1.0 for value in odds):
        return None
    return devig_decimal_odds(odds)[0]  # type: ignore[arg-type]


def build_scoreline_history(db_path: Path) -> list[ScorelineRow]:
    """Build leakage-safe pre-match Poisson scoreline estimates.

    Team home/away role histories and league scoring baselines are frozen for
    an entire date before any results from that date are incorporated.
    """
    conn = sqlite3.connect(db_path)
    try:
        records = conn.execute(
            """
            SELECT match_id, season_start_year, match_date, home_team, away_team,
                   fthg, ftag, ftr, raw_json
            FROM matches
            ORDER BY match_date, match_id
            """
        ).fetchall()
    finally:
        conn.close()

    states: dict[str, TeamRoleState] = defaultdict(TeamRoleState.empty)
    league_home: deque[float] = deque(maxlen=LEAGUE_WINDOW)
    league_away: deque[float] = deque(maxlen=LEAGUE_WINDOW)
    rows: list[ScorelineRow] = []

    i = 0
    while i < len(records):
        match_date = str(records[i][2])
        j = i
        while j < len(records) and str(records[j][2]) == match_date:
            j += 1
        day = records[i:j]

        league_home_mean = _mean(league_home, FALLBACK_HOME_GOALS)
        league_away_mean = _mean(league_away, FALLBACK_AWAY_GOALS)

        for record in day:
            match_id, season, current_date, home, away, _, _, result, raw_json = record
            home = str(home)
            away = str(away)
            lambda_home, lambda_away = expected_goals(
                home_history=states[home].home_games,
                away_history=states[away].away_games,
                league_home_goals=league_home_mean,
                league_away_goals=league_away_mean,
            )
            probs, modal = scoreline_distribution(lambda_home, lambda_away)
            rows.append(
                ScorelineRow(
                    match_id=str(match_id),
                    season_start_year=int(season),
                    match_date=str(current_date),
                    home_team=home,
                    away_team=away,
                    result=str(result),
                    expected_home_goals=lambda_home,
                    expected_away_goals=lambda_away,
                    home_prob=probs[0],
                    draw_prob=probs[1],
                    away_prob=probs[2],
                    top_score_home=modal[0],
                    top_score_away=modal[1],
                    top_score_prob=modal[2],
                    market_probs=_parse_market_probs(str(raw_json)),
                )
            )

        # Only now do this date's results become available.
        for record in day:
            _, _, _, home, away, home_goals, away_goals, _, _ = record
            home_goals = float(home_goals)
            away_goals = float(away_goals)
            states[str(home)].home_games.append(
                ScoreGame(goals_for=home_goals, goals_against=away_goals)
            )
            states[str(away)].away_games.append(
                ScoreGame(goals_for=away_goals, goals_against=home_goals)
            )
            league_home.append(home_goals)
            league_away.append(away_goals)
        i = j

    return rows


def _top_label_ece(items: list[tuple[tuple[float, float, float], str]], bins: int = 10) -> float:
    if not items:
        return 0.0
    total = len(items)
    ece = 0.0
    for bin_index in range(bins):
        lo = bin_index / bins
        hi = (bin_index + 1) / bins
        bucket: list[tuple[float, bool]] = []
        for probs, result in items:
            idx = max(range(3), key=lambda k: probs[k])
            confidence = probs[idx]
            if (lo <= confidence < hi) or (bin_index == bins - 1 and confidence == hi):
                bucket.append((confidence, CLASS_ORDER[idx] == result))
        if bucket:
            mean_conf = sum(item[0] for item in bucket) / len(bucket)
            accuracy = sum(1.0 for item in bucket if item[1]) / len(bucket)
            ece += (len(bucket) / total) * abs(accuracy - mean_conf)
    return ece


def _metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    if not items:
        return {"matches": 0, "log_loss": None, "brier": None, "accuracy": None, "top_label_ece": None}
    scores = [score_probabilities(probs, result) for probs, result in items]
    n = len(scores)
    return {
        "matches": n,
        "log_loss": sum(score.log_loss for score in scores) / n,
        "brier": sum(score.brier for score in scores) / n,
        "accuracy": sum(score.correct for score in scores) / n,
        "top_label_ece": _top_label_ece(items),
    }


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def walk_forward_scoreline(db_path: Path, *, min_train_seasons: int = 3) -> dict[str, object]:
    rows = build_scoreline_history(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    test_seasons = set(seasons[min_train_seasons:])
    test = [row for row in rows if row.season_start_year in test_seasons]
    model_items = [((row.home_prob, row.draw_prob, row.away_prob), row.result) for row in test]
    paired_model = [
        ((row.home_prob, row.draw_prob, row.away_prob), row.result)
        for row in test
        if row.market_probs is not None
    ]
    paired_market = [(row.market_probs, row.result) for row in test if row.market_probs is not None]
    paired_market = [(probs, result) for probs, result in paired_market if probs is not None]

    season_reports: list[dict[str, object]] = []
    for season in sorted(test_seasons):
        season_rows = [row for row in test if row.season_start_year == season]
        model = [((row.home_prob, row.draw_prob, row.away_prob), row.result) for row in season_rows]
        market = [(row.market_probs, row.result) for row in season_rows if row.market_probs is not None]
        market = [(probs, result) for probs, result in market if probs is not None]
        model_paired = [
            ((row.home_prob, row.draw_prob, row.away_prob), row.result)
            for row in season_rows
            if row.market_probs is not None
        ]
        model_m = _metrics(model)
        model_paired_m = _metrics(model_paired)
        market_m = _metrics(market)  # type: ignore[arg-type]
        season_reports.append(
            {
                "test_season_start_year": season,
                "test_matches": len(season_rows),
                "scoreline": model_m,
                "paired_b365_pre_closing": {
                    "matches": model_paired_m["matches"],
                    "model_log_loss": model_paired_m["log_loss"],
                    "market_log_loss": market_m["log_loss"],
                    "log_loss_delta_model_minus_market": _delta(model_paired_m["log_loss"], market_m["log_loss"]),
                    "model_brier": model_paired_m["brier"],
                    "market_brier": market_m["brier"],
                    "brier_delta_model_minus_market": _delta(model_paired_m["brier"], market_m["brier"]),
                },
            }
        )

    overall = _metrics(model_items)
    paired_model_m = _metrics(paired_model)
    paired_market_m = _metrics(paired_market)  # type: ignore[arg-type]
    latest = sorted(rows, key=lambda row: (row.match_date, row.match_id))[-20:]

    return {
        "model": "independent_poisson_scoreline_v1",
        "parameters": {
            "team_role_window": TEAM_ROLE_WINDOW,
            "league_window": LEAGUE_WINDOW,
            "prior_weight": PRIOR_WEIGHT,
            "fallback_home_goals": FALLBACK_HOME_GOALS,
            "fallback_away_goals": FALLBACK_AWAY_GOALS,
            "min_lambda": MIN_LAMBDA,
            "max_lambda": MAX_LAMBDA,
            "max_score": MAX_SCORE,
        },
        "hyperparameter_policy": "all v1 parameters fixed before OOS evaluation; no OOS tuning",
        "model_policy": "venue-role attack/defence strengths -> independent Poisson score grid -> H/D/A; no bookmaker inputs and no fitted H/D/A calibration layer",
        "same_day_policy": "all states for a date are frozen before same-date results update team or league scoring histories",
        "promotion_policy": "unseen teams begin at league-average scoring priors; no invented lower-league strength in EPL-only v1",
        "evaluation_policy": "first three seasons treated as warm-up; all later seasons evaluated chronologically",
        "overall_model": overall,
        "paired_overall": {
            "matches": paired_model_m["matches"],
            "model_log_loss": paired_model_m["log_loss"],
            "market_log_loss": paired_market_m["log_loss"],
            "log_loss_delta_model_minus_market": _delta(paired_model_m["log_loss"], paired_market_m["log_loss"]),
            "model_brier": paired_model_m["brier"],
            "market_brier": paired_market_m["brier"],
            "brier_delta_model_minus_market": _delta(paired_model_m["brier"], paired_market_m["brier"]),
        },
        "latest_scoreline_estimates": [
            {
                "match_id": row.match_id,
                "date": row.match_date,
                "home_team": row.home_team,
                "away_team": row.away_team,
                "expected_home_goals": row.expected_home_goals,
                "expected_away_goals": row.expected_away_goals,
                "home_prob": row.home_prob,
                "draw_prob": row.draw_prob,
                "away_prob": row.away_prob,
                "modal_score": f"{row.top_score_home}-{row.top_score_away}",
                "modal_score_prob": row.top_score_prob,
            }
            for row in latest
        ],
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Leakage-safe EPL Poisson scoreline model.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_scoreline(args.database, min_train_seasons=args.min_train_seasons)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote scoreline report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
