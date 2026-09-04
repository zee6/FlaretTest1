from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from football1.market_baseline import devig_decimal_odds, score_probabilities


BASE_RATING = 1500.0
ELO_SCALE = 400.0
K_FACTOR = 20.0
HOME_ADVANTAGE = 75.0
SEASON_CARRY = 0.75
CLASS_ORDER = ("H", "D", "A")


@dataclass(frozen=True)
class EloRow:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    home_rating: float
    away_rating: float
    elo_diff: float
    expected_home_score: float
    market_probs: tuple[float, float, float] | None


def expected_home_score(
    home_rating: float,
    away_rating: float,
    *,
    home_advantage: float = HOME_ADVANTAGE,
    scale: float = ELO_SCALE,
) -> float:
    """Classic Elo expected score for the home side, with draws worth 0.5."""
    exponent = -((home_rating + home_advantage) - away_rating) / scale
    return 1.0 / (1.0 + 10.0**exponent)


def actual_home_score(result: str) -> float:
    if result == "H":
        return 1.0
    if result == "D":
        return 0.5
    if result == "A":
        return 0.0
    raise ValueError(f"Unknown result: {result!r}")


def update_ratings(
    home_rating: float,
    away_rating: float,
    result: str,
    *,
    k_factor: float = K_FACTOR,
    home_advantage: float = HOME_ADVANTAGE,
) -> tuple[float, float]:
    expected = expected_home_score(
        home_rating,
        away_rating,
        home_advantage=home_advantage,
    )
    actual = actual_home_score(result)
    change = k_factor * (actual - expected)
    return home_rating + change, away_rating - change


def regress_rating(
    rating: float,
    *,
    base_rating: float = BASE_RATING,
    season_carry: float = SEASON_CARRY,
) -> float:
    if not 0.0 <= season_carry <= 1.0:
        raise ValueError("season_carry must be between 0 and 1")
    return base_rating + season_carry * (rating - base_rating)


def _parse_market_probs(raw_json: str) -> tuple[float, float, float] | None:
    raw = json.loads(raw_json)
    try:
        odds = tuple(float(str(raw.get(name, "")).strip()) for name in ("B365H", "B365D", "B365A"))
    except (TypeError, ValueError):
        return None
    if any((not math.isfinite(x)) or x <= 1.0 for x in odds):
        return None
    return devig_decimal_odds(odds)[0]  # type: ignore[arg-type]


def build_elo_history(
    db_path: Path,
    *,
    base_rating: float = BASE_RATING,
    k_factor: float = K_FACTOR,
    home_advantage: float = HOME_ADVANTAGE,
    season_carry: float = SEASON_CARRY,
) -> tuple[list[EloRow], dict[str, float]]:
    """Build leakage-safe pre-match Elo rows in chronological order.

    Every match on the same date is snapshotted from ratings that existed at
    the start of that date. Results from that date are applied only after all
    same-date snapshots have been created.
    """
    conn = sqlite3.connect(db_path)
    try:
        records = conn.execute(
            """
            SELECT match_id, season_start_year, match_date,
                   home_team, away_team, ftr, raw_json
            FROM matches
            ORDER BY season_start_year, match_date, match_id
            """
        ).fetchall()
    finally:
        conn.close()

    ratings: dict[str, float] = {}
    rows: list[EloRow] = []
    current_season: int | None = None
    i = 0

    while i < len(records):
        season = int(records[i][1])
        date = str(records[i][2])

        if current_season != season:
            if current_season is not None:
                ratings = {
                    team: regress_rating(
                        rating,
                        base_rating=base_rating,
                        season_carry=season_carry,
                    )
                    for team, rating in ratings.items()
                }
            current_season = season

        j = i
        day_records: list[tuple[object, ...]] = []
        while j < len(records) and int(records[j][1]) == season and str(records[j][2]) == date:
            day_records.append(records[j])
            j += 1

        snapshots: list[tuple[str, str, str, float, float]] = []
        for record in day_records:
            match_id, season_start_year, match_date, home, away, result, raw_json = record
            home = str(home)
            away = str(away)
            home_rating = ratings.get(home, base_rating)
            away_rating = ratings.get(away, base_rating)
            diff = (home_rating + home_advantage) - away_rating
            expected = expected_home_score(
                home_rating,
                away_rating,
                home_advantage=home_advantage,
            )
            rows.append(
                EloRow(
                    match_id=str(match_id),
                    season_start_year=int(season_start_year),
                    match_date=str(match_date),
                    home_team=home,
                    away_team=away,
                    result=str(result),
                    home_rating=home_rating,
                    away_rating=away_rating,
                    elo_diff=diff,
                    expected_home_score=expected,
                    market_probs=_parse_market_probs(str(raw_json)),
                )
            )
            snapshots.append((home, away, str(result), home_rating, away_rating))

        # Apply results only after every fixture on this date has been frozen.
        for home, away, result, home_rating, away_rating in snapshots:
            new_home, new_away = update_ratings(
                home_rating,
                away_rating,
                result,
                k_factor=k_factor,
                home_advantage=home_advantage,
            )
            ratings[home] = new_home
            ratings[away] = new_away

        i = j

    return rows, ratings


def build_elo_rows(db_path: Path, **kwargs: float) -> list[EloRow]:
    return build_elo_history(db_path, **kwargs)[0]


def _x(row: EloRow) -> list[float]:
    # One deliberately simple dimension: effective rating gap in Elo-scale units.
    return [row.elo_diff / ELO_SCALE]


def _fit_probability_layer(rows: list[EloRow]) -> LogisticRegression:
    model = LogisticRegression(
        solver="lbfgs",
        C=1.0,
        max_iter=2000,
        random_state=0,
    )
    model.fit(np.asarray([_x(row) for row in rows], dtype=float), [row.result for row in rows])
    return model


def _predict_probs(model: LogisticRegression, row: EloRow) -> tuple[float, float, float]:
    raw = model.predict_proba(np.asarray([_x(row)], dtype=float))[0]
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
        if not bucket:
            continue
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
        "log_loss": sum(s.log_loss for s in scores) / n,
        "brier": sum(s.brier for s in scores) / n,
        "accuracy": sum(s.correct for s in scores) / n,
        "top_label_ece": _top_label_ece(items),
    }


def walk_forward_elo(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    base_rating: float = BASE_RATING,
    k_factor: float = K_FACTOR,
    home_advantage: float = HOME_ADVANTAGE,
    season_carry: float = SEASON_CARRY,
) -> dict[str, object]:
    rows, final_ratings = build_elo_history(
        db_path,
        base_rating=base_rating,
        k_factor=k_factor,
        home_advantage=home_advantage,
        season_carry=season_carry,
    )
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_model: list[tuple[tuple[float, float, float], str]] = []
    all_model_paired: list[tuple[tuple[float, float, float], str]] = []
    all_market_paired: list[tuple[tuple[float, float, float], str]] = []
    season_reports: list[dict[str, object]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train = [row for row in rows if row.season_start_year in seasons[:test_index]]
        test = [row for row in rows if row.season_start_year == test_season]
        model = _fit_probability_layer(train)

        model_items = [(_predict_probs(model, row), row.result) for row in test]
        paired_model = [
            (_predict_probs(model, row), row.result)
            for row in test
            if row.market_probs is not None
        ]
        paired_market = [
            (row.market_probs, row.result)
            for row in test
            if row.market_probs is not None
        ]
        paired_market = [(probs, result) for probs, result in paired_market if probs is not None]

        all_model.extend(model_items)
        all_model_paired.extend(paired_model)
        all_market_paired.extend(paired_market)  # type: ignore[arg-type]

        model_m = _metrics(model_items)
        paired_model_m = _metrics(paired_model)
        paired_market_m = _metrics(all([]) if False else paired_market)  # keep type narrow for mypy-free runtime
        season_reports.append(
            {
                "test_season_start_year": test_season,
                "train_matches": len(train),
                "test_matches": len(test),
                "elo": model_m,
                "paired_b365_pre_closing": {
                    "matches": paired_model_m["matches"],
                    "elo_log_loss": paired_model_m["log_loss"],
                    "market_log_loss": paired_market_m["log_loss"],
                    "log_loss_delta_elo_minus_market": (
                        float(paired_model_m["log_loss"]) - float(paired_market_m["log_loss"])
                        if paired_model_m["log_loss"] is not None and paired_market_m["log_loss"] is not None
                        else None
                    ),
                    "elo_brier": paired_model_m["brier"],
                    "market_brier": paired_market_m["brier"],
                    "brier_delta_elo_minus_market": (
                        float(paired_model_m["brier"]) - float(paired_market_m["brier"])
                        if paired_model_m["brier"] is not None and paired_market_m["brier"] is not None
                        else None
                    ),
                },
            }
        )

    overall_model = _metrics(all_model)
    paired_model_m = _metrics(all_model_paired)
    paired_market_m = _metrics(all_market_paired)

    return {
        "model": "elo_1x2_v1",
        "elo_parameters": {
            "base_rating": base_rating,
            "k_factor": k_factor,
            "scale": ELO_SCALE,
            "home_advantage": home_advantage,
            "season_carry": season_carry,
        },
        "hyperparameter_policy": "v1 parameters fixed before OOS evaluation; no OOS tuning",
        "rating_policy": "classic result-only Elo; H=1, D=0.5, A=0; no goal-margin multiplier",
        "promotion_policy": "previously unseen teams enter at neutral 1500 in EPL-only v1; no invented lower-league adjustment",
        "probability_layer": "multinomial logistic calibration from one pre-match effective Elo gap feature, fit only on earlier seasons",
        "split_policy": "walk-forward by season; each held-out season is predicted using a calibration layer fit only on earlier seasons",
        "same_day_policy": "all Elo states for a date are frozen before any result from that date updates ratings",
        "overall_model": overall_model,
        "paired_overall": {
            "matches": paired_model_m["matches"],
            "elo_log_loss": paired_model_m["log_loss"],
            "market_log_loss": paired_market_m["log_loss"],
            "log_loss_delta_elo_minus_market": (
                float(paired_model_m["log_loss"]) - float(paired_market_m["log_loss"])
                if paired_model_m["log_loss"] is not None and paired_market_m["log_loss"] is not None
                else None
            ),
            "elo_brier": paired_model_m["brier"],
            "market_brier": paired_market_m["brier"],
            "brier_delta_elo_minus_market": (
                float(paired_model_m["brier"]) - float(paired_market_m["brier"])
                if paired_model_m["brier"] is not None and paired_market_m["brier"] is not None
                else None
            ),
        },
        "final_ratings": [
            {"team": team, "rating": rating}
            for team, rating in sorted(final_ratings.items(), key=lambda item: (-item[1], item[0]))
        ],
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Leakage-safe walk-forward EPL Elo baseline.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_elo(args.database, min_train_seasons=args.min_train_seasons)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote Elo report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
