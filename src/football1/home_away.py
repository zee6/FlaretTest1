from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from football1.market_baseline import devig_decimal_odds, score_probabilities


NEUTRAL_PPG = 1.35
NEUTRAL_GOALS = 1.35
PRIOR_WEIGHT = 2.0
CLASS_ORDER = ("H", "D", "A")
FEATURE_NAMES = (
    "venue_ppg5_diff",
    "venue_gd5_diff",
    "venue_ppg10_diff",
    "venue_gd10_diff",
)


@dataclass(frozen=True)
class VenueGame:
    points: float
    goals_for: float
    goals_against: float


@dataclass
class VenueState:
    home_games: deque[VenueGame]
    away_games: deque[VenueGame]

    @classmethod
    def empty(cls) -> "VenueState":
        return cls(home_games=deque(maxlen=10), away_games=deque(maxlen=10))


@dataclass(frozen=True)
class HomeAwayRow:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    venue_ppg5_diff: float
    venue_gd5_diff: float
    venue_ppg10_diff: float
    venue_gd10_diff: float
    market_probs: tuple[float, float, float] | None


def _points(result: str, *, home: bool) -> float:
    if result == "D":
        return 1.0
    if (home and result == "H") or ((not home) and result == "A"):
        return 3.0
    return 0.0


def _smoothed_mean(values: list[float], neutral: float) -> float:
    return (sum(values) + PRIOR_WEIGHT * neutral) / (len(values) + PRIOR_WEIGHT)


def _summary(games: deque[VenueGame], n: int) -> tuple[float, float]:
    recent = list(games)[-n:]
    ppg = _smoothed_mean([game.points for game in recent], NEUTRAL_PPG)
    gf = _smoothed_mean([game.goals_for for game in recent], NEUTRAL_GOALS)
    ga = _smoothed_mean([game.goals_against for game in recent], NEUTRAL_GOALS)
    return ppg, gf - ga


def _parse_market_probs(raw_json: str) -> tuple[float, float, float] | None:
    raw = json.loads(raw_json)
    try:
        odds = tuple(float(str(raw.get(name, "")).strip()) for name in ("B365H", "B365D", "B365A"))
    except (TypeError, ValueError):
        return None
    if any((not math.isfinite(x)) or x <= 1.0 for x in odds):
        return None
    return devig_decimal_odds(odds)[0]  # type: ignore[arg-type]


def build_home_away_history(db_path: Path) -> tuple[list[HomeAwayRow], dict[str, VenueState]]:
    """Build venue-specific pre-match form using only prior completed dates."""
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

    states: dict[str, VenueState] = defaultdict(VenueState.empty)
    rows: list[HomeAwayRow] = []
    i = 0
    while i < len(records):
        date = str(records[i][2])
        j = i
        while j < len(records) and str(records[j][2]) == date:
            j += 1
        day = records[i:j]

        for record in day:
            match_id, season, match_date, home, away, _, _, result, raw_json = record
            home_state = states[str(home)]
            away_state = states[str(away)]
            home_ppg5, home_gd5 = _summary(home_state.home_games, 5)
            away_ppg5, away_gd5 = _summary(away_state.away_games, 5)
            home_ppg10, home_gd10 = _summary(home_state.home_games, 10)
            away_ppg10, away_gd10 = _summary(away_state.away_games, 10)
            rows.append(
                HomeAwayRow(
                    match_id=str(match_id),
                    season_start_year=int(season),
                    match_date=str(match_date),
                    home_team=str(home),
                    away_team=str(away),
                    result=str(result),
                    venue_ppg5_diff=home_ppg5 - away_ppg5,
                    venue_gd5_diff=home_gd5 - away_gd5,
                    venue_ppg10_diff=home_ppg10 - away_ppg10,
                    venue_gd10_diff=home_gd10 - away_gd10,
                    market_probs=_parse_market_probs(str(raw_json)),
                )
            )

        # Results from this date become available only after all same-date rows
        # have been snapshotted.
        for record in day:
            _, _, _, home, away, fthg, ftag, result, _ = record
            states[str(home)].home_games.append(
                VenueGame(
                    points=_points(str(result), home=True),
                    goals_for=float(fthg),
                    goals_against=float(ftag),
                )
            )
            states[str(away)].away_games.append(
                VenueGame(
                    points=_points(str(result), home=False),
                    goals_for=float(ftag),
                    goals_against=float(fthg),
                )
            )
        i = j

    return rows, dict(states)


def build_home_away_rows(db_path: Path) -> list[HomeAwayRow]:
    return build_home_away_history(db_path)[0]


def feature_vector(row: HomeAwayRow) -> list[float]:
    return [float(getattr(row, name)) for name in FEATURE_NAMES]


def _fit_probability_layer(rows: list[HomeAwayRow]) -> LogisticRegression:
    model = LogisticRegression(solver="lbfgs", C=1.0, max_iter=2000, random_state=0)
    model.fit(np.asarray([feature_vector(row) for row in rows], dtype=float), [row.result for row in rows])
    return model


def _predict_probs(model: LogisticRegression, row: HomeAwayRow) -> tuple[float, float, float]:
    raw = model.predict_proba(np.asarray([feature_vector(row)], dtype=float))[0]
    mapping = {str(label): float(prob) for label, prob in zip(model.classes_, raw)}
    return tuple(mapping[label] for label in CLASS_ORDER)  # type: ignore[return-value]


def _top_label_ece(items: list[tuple[tuple[float, float, float], str]], bins: int = 10) -> float:
    if not items:
        return 0.0
    total = len(items)
    ece = 0.0
    for lower_index in range(bins):
        lo = lower_index / bins
        hi = (lower_index + 1) / bins
        bucket: list[tuple[float, bool]] = []
        for probs, result in items:
            idx = max(range(3), key=lambda k: probs[k])
            confidence = probs[idx]
            if (lo <= confidence < hi) or (lower_index == bins - 1 and confidence == hi):
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


def walk_forward_home_away(db_path: Path, *, min_train_seasons: int = 3) -> dict[str, object]:
    rows, final_states = build_home_away_history(db_path)
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
                "home_away": model_m,
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

    venue_table: list[dict[str, object]] = []
    for team, state in final_states.items():
        home_ppg, home_gd = _summary(state.home_games, 10)
        away_ppg, away_gd = _summary(state.away_games, 10)
        venue_table.append(
            {
                "team": team,
                "home_ppg10": home_ppg,
                "home_gd10": home_gd,
                "away_ppg10": away_ppg,
                "away_gd10": away_gd,
            }
        )

    return {
        "model": "home_away_form_v1",
        "feature_names": list(FEATURE_NAMES),
        "feature_policy": "venue-specific EPL results only; last 5/10 home matches for home side and last 5/10 away matches for away side; neutral priors weight 2",
        "same_day_policy": "all fixtures on a date are frozen before same-date results update venue histories",
        "promotion_policy": "teams with no EPL history begin from neutral priors; lower-league venue form is not invented in v1",
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
        "current_venue_table": sorted(venue_table, key=lambda row: str(row["team"])),
        "seasons": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Leakage-safe EPL home/away form module.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_home_away(args.database, min_train_seasons=args.min_train_seasons)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote home/away report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
