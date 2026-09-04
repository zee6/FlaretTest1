from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from football1.market_baseline import devig_decimal_odds, score_probabilities


HALF_LIFE_DAYS = 730.0
PRIOR_WEIGHT = 3.0
CLASS_ORDER = ("H", "D", "A")
FEATURE_NAMES = (
    "pair_score_edge",
    "pair_goal_diff",
    "same_venue_score_edge",
    "pair_history_strength",
    "same_venue_history_strength",
)


@dataclass(frozen=True)
class Meeting:
    match_date: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class HeadToHeadRow:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    pair_score_edge: float
    pair_goal_diff: float
    same_venue_score_edge: float
    pair_history_strength: float
    same_venue_history_strength: float
    market_probs: tuple[float, float, float] | None


def _pair_key(team_a: str, team_b: str) -> tuple[str, str]:
    return tuple(sorted((team_a, team_b)))  # type: ignore[return-value]


def _weight(prior_date: str, current_date: str) -> float:
    days = max(0, (date.fromisoformat(current_date) - date.fromisoformat(prior_date)).days)
    return 0.5 ** (days / HALF_LIFE_DAYS)


def _oriented_score(meeting: Meeting, perspective_team: str) -> tuple[float, float]:
    if meeting.home_team == perspective_team:
        goals_for = meeting.home_goals
        goals_against = meeting.away_goals
    elif meeting.away_team == perspective_team:
        goals_for = meeting.away_goals
        goals_against = meeting.home_goals
    else:
        raise ValueError(f"{perspective_team!r} not present in meeting")

    if goals_for > goals_against:
        score = 1.0
    elif goals_for == goals_against:
        score = 0.5
    else:
        score = 0.0
    return score, float(goals_for - goals_against)


def _summarize(
    meetings: list[Meeting],
    *,
    perspective_team: str,
    current_date: str,
) -> tuple[float, float, float]:
    weighted_score = 0.0
    weighted_gd = 0.0
    effective_count = 0.0
    for meeting in meetings:
        weight = _weight(meeting.match_date, current_date)
        score, goal_diff = _oriented_score(meeting, perspective_team)
        weighted_score += weight * score
        weighted_gd += weight * goal_diff
        effective_count += weight

    denominator = effective_count + PRIOR_WEIGHT
    # Neutral prior means score 0.5 and goal difference 0.
    score = (weighted_score + PRIOR_WEIGHT * 0.5) / denominator
    goal_diff = weighted_gd / denominator
    strength = effective_count / denominator
    return score - 0.5, goal_diff, strength


def _parse_market_probs(raw_json: str) -> tuple[float, float, float] | None:
    raw = json.loads(raw_json)
    try:
        odds = tuple(float(str(raw.get(name, "")).strip()) for name in ("B365H", "B365D", "B365A"))
    except (TypeError, ValueError):
        return None
    if any((not math.isfinite(value)) or value <= 1.0 for value in odds):
        return None
    return devig_decimal_odds(odds)[0]  # type: ignore[arg-type]


def build_head_to_head_history(db_path: Path) -> list[HeadToHeadRow]:
    """Build pre-match H2H features using only earlier completed dates.

    Pair history is orientation-aware at scoring time, so a prior reverse
    fixture is correctly viewed from the current home team's perspective.
    Same-venue history contains only earlier fixtures with the same home and
    away roles. A fixed neutral prior prevents tiny samples dominating.
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

    pair_history: dict[tuple[str, str], list[Meeting]] = {}
    venue_history: dict[tuple[str, str], list[Meeting]] = {}
    rows: list[HeadToHeadRow] = []

    i = 0
    while i < len(records):
        current_date = str(records[i][2])
        j = i
        while j < len(records) and str(records[j][2]) == current_date:
            j += 1
        day = records[i:j]

        for record in day:
            match_id, season, match_date, home, away, _, _, result, raw_json = record
            home = str(home)
            away = str(away)
            pair = pair_history.get(_pair_key(home, away), [])
            same_venue = venue_history.get((home, away), [])

            pair_score, pair_gd, pair_strength = _summarize(
                pair,
                perspective_team=home,
                current_date=str(match_date),
            )
            venue_score, _, venue_strength = _summarize(
                same_venue,
                perspective_team=home,
                current_date=str(match_date),
            )
            rows.append(
                HeadToHeadRow(
                    match_id=str(match_id),
                    season_start_year=int(season),
                    match_date=str(match_date),
                    home_team=home,
                    away_team=away,
                    result=str(result),
                    pair_score_edge=pair_score,
                    pair_goal_diff=pair_gd,
                    same_venue_score_edge=venue_score,
                    pair_history_strength=pair_strength,
                    same_venue_history_strength=venue_strength,
                    market_probs=_parse_market_probs(str(raw_json)),
                )
            )

        # Freeze the entire date before any result becomes H2H history.
        for record in day:
            _, _, match_date, home, away, home_goals, away_goals, _, _ = record
            meeting = Meeting(
                match_date=str(match_date),
                home_team=str(home),
                away_team=str(away),
                home_goals=int(home_goals),
                away_goals=int(away_goals),
            )
            pair_history.setdefault(_pair_key(str(home), str(away)), []).append(meeting)
            venue_history.setdefault((str(home), str(away)), []).append(meeting)
        i = j

    return rows


def feature_vector(row: HeadToHeadRow) -> list[float]:
    return [float(getattr(row, name)) for name in FEATURE_NAMES]


def _fit_probability_layer(rows: list[HeadToHeadRow]) -> LogisticRegression:
    model = LogisticRegression(solver="lbfgs", C=1.0, max_iter=2000, random_state=0)
    model.fit(np.asarray([feature_vector(row) for row in rows], dtype=float), [row.result for row in rows])
    return model


def _predict_probs(model: LogisticRegression, row: HeadToHeadRow) -> tuple[float, float, float]:
    raw = model.predict_proba(np.asarray([feature_vector(row)], dtype=float))[0]
    mapping = {str(label): float(prob) for label, prob in zip(model.classes_, raw)}
    return tuple(mapping[label] for label in CLASS_ORDER)  # type: ignore[return-value]


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


def walk_forward_head_to_head(db_path: Path, *, min_train_seasons: int = 3) -> dict[str, object]:
    rows = build_head_to_head_history(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_model: list[tuple[tuple[float, float, float], str]] = []
    all_model_paired: list[tuple[tuple[float, float, float], str]] = []
    all_market_paired: list[tuple[tuple[float, float, float], str]] = []
    reports: list[dict[str, object]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train = [row for row in rows if row.season_start_year in seasons[:test_index]]
        test = [row for row in rows if row.season_start_year == test_season]
        model = _fit_probability_layer(train)

        model_items = [(_predict_probs(model, row), row.result) for row in test]
        paired_model = [(_predict_probs(model, row), row.result) for row in test if row.market_probs is not None]
        paired_market = [(row.market_probs, row.result) for row in test if row.market_probs is not None]
        paired_market = [(probs, result) for probs, result in paired_market if probs is not None]

        all_model.extend(model_items)
        all_model_paired.extend(paired_model)
        all_market_paired.extend(paired_market)  # type: ignore[arg-type]
        model_m = _metrics(model_items)
        paired_model_m = _metrics(paired_model)
        paired_market_m = _metrics(paired_market)  # type: ignore[arg-type]
        reports.append(
            {
                "test_season_start_year": test_season,
                "train_matches": len(train),
                "test_matches": len(test),
                "head_to_head": model_m,
                "paired_b365_pre_closing": {
                    "matches": paired_model_m["matches"],
                    "model_log_loss": paired_model_m["log_loss"],
                    "market_log_loss": paired_market_m["log_loss"],
                    "log_loss_delta_model_minus_market": _delta(paired_model_m["log_loss"], paired_market_m["log_loss"]),
                    "model_brier": paired_model_m["brier"],
                    "market_brier": paired_market_m["brier"],
                    "brier_delta_model_minus_market": _delta(paired_model_m["brier"], paired_market_m["brier"]),
                },
            }
        )

    model_m = _metrics(all_model)
    paired_model_m = _metrics(all_model_paired)
    paired_market_m = _metrics(all_market_paired)
    return {
        "model": "head_to_head_v1",
        "feature_names": list(FEATURE_NAMES),
        "half_life_days": HALF_LIFE_DAYS,
        "prior_weight": PRIOR_WEIGHT,
        "feature_policy": "recency-weighted prior meetings, neutral Bayesian-style shrinkage, overall pair plus exact home-away role history",
        "same_day_policy": "all fixtures on a date are frozen before same-date results enter H2H history",
        "interpretation_policy": "H2H is a candidate context signal only; small samples are deliberately shrunk toward neutral",
        "split_policy": "walk-forward by season; probability layer trained only on earlier seasons",
        "overall_model": model_m,
        "paired_overall": {
            "matches": paired_model_m["matches"],
            "model_log_loss": paired_model_m["log_loss"],
            "market_log_loss": paired_market_m["log_loss"],
            "log_loss_delta_model_minus_market": _delta(paired_model_m["log_loss"], paired_market_m["log_loss"]),
            "model_brier": paired_model_m["brier"],
            "market_brier": paired_market_m["brier"],
            "brier_delta_model_minus_market": _delta(paired_model_m["brier"], paired_market_m["brier"]),
        },
        "seasons": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Leakage-safe EPL head-to-head module.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_head_to_head(args.database, min_train_seasons=args.min_train_seasons)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote head-to-head report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
