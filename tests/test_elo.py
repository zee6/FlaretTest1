from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

import pytest

from football1.elo import (
    BASE_RATING,
    HOME_ADVANTAGE,
    SEASON_CARRY,
    build_elo_rows,
    expected_home_score,
    regress_rating,
    update_ratings,
    walk_forward_elo,
)


def _db(path: Path, rows: list[tuple[str, int, str, str, str, str]]) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE matches (
                match_id TEXT PRIMARY KEY,
                season_start_year INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                ftr TEXT NOT NULL,
                raw_json TEXT NOT NULL
            )
            """
        )
        for match_id, season, date, home, away, result in rows:
            raw = json.dumps({"B365H": "2.20", "B365D": "3.40", "B365A": "3.30"})
            conn.execute(
                "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?)",
                (match_id, season, date, home, away, result, raw),
            )
        conn.commit()
    finally:
        conn.close()
    return path


def test_equal_ratings_are_even_on_neutral_ground() -> None:
    assert expected_home_score(1500.0, 1500.0, home_advantage=0.0) == pytest.approx(0.5)
    assert expected_home_score(1500.0, 1500.0) > 0.5


def test_elo_update_is_zero_sum() -> None:
    home, away = update_ratings(1500.0, 1500.0, "H")
    assert home > 1500.0
    assert away < 1500.0
    assert home + away == pytest.approx(3000.0)


def test_same_date_is_frozen_before_results_update(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "same_day.sqlite",
        [
            ("m1", 2024, "2024-08-10", "Alpha", "Bravo", "H"),
            # Synthetic double fixture is intentional: it proves that m1's
            # result cannot alter Alpha's pre-match state for another row on
            # the same date.
            ("m2", 2024, "2024-08-10", "Alpha", "Charlie", "A"),
        ],
    )
    rows = build_elo_rows(db)
    assert rows[0].home_rating == pytest.approx(BASE_RATING)
    assert rows[1].home_rating == pytest.approx(BASE_RATING)
    assert rows[1].away_rating == pytest.approx(BASE_RATING)


def test_new_team_is_neutral_and_existing_team_regresses_between_seasons(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "seasons.sqlite",
        [
            ("m1", 2024, "2024-08-10", "Alpha", "Bravo", "H"),
            ("m2", 2025, "2025-08-10", "Alpha", "Promoted", "D"),
        ],
    )
    rows = build_elo_rows(db)
    post_alpha, _ = update_ratings(BASE_RATING, BASE_RATING, "H")
    expected_alpha = regress_rating(post_alpha, season_carry=SEASON_CARRY)
    assert rows[1].home_rating == pytest.approx(expected_alpha)
    assert rows[1].away_rating == pytest.approx(BASE_RATING)
    assert rows[1].elo_diff == pytest.approx(expected_alpha + HOME_ADVANTAGE - BASE_RATING)


def test_walk_forward_elo_uses_only_later_season_as_test(tmp_path: Path) -> None:
    rows: list[tuple[str, int, str, str, str, str]] = []
    # Four seasons, with all three outcomes represented in every season so the
    # multinomial probability layer is well-defined in each training window.
    for offset, season in enumerate((2022, 2023, 2024, 2025)):
        outcomes = ("H", "D", "A", "H", "D", "A")
        fixtures = (
            ("Alpha", "Bravo"),
            ("Charlie", "Delta"),
            ("Alpha", "Charlie"),
            ("Bravo", "Delta"),
            ("Alpha", "Delta"),
            ("Bravo", "Charlie"),
        )
        for i, ((home, away), result) in enumerate(zip(fixtures, outcomes), start=1):
            rows.append((f"{season}-{i}", season, f"{season}-08-{9+i:02d}", home, away, result))

    db = _db(tmp_path / "walk.sqlite", rows)
    report = walk_forward_elo(db, min_train_seasons=3)

    assert report["model"] == "elo_1x2_v1"
    assert report["overall_model"]["matches"] == 6
    assert report["paired_overall"]["matches"] == 6
    assert len(report["seasons"]) == 1
    assert report["seasons"][0]["test_season_start_year"] == 2025
    assert report["seasons"][0]["train_matches"] == 18
    assert report["seasons"][0]["test_matches"] == 6
    assert math.isfinite(float(report["overall_model"]["log_loss"]))
