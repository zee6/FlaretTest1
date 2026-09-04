from __future__ import annotations

import json
import sqlite3
from collections import deque
from pathlib import Path

import pytest

from football1.scoreline import (
    FALLBACK_AWAY_GOALS,
    FALLBACK_HOME_GOALS,
    ScoreGame,
    build_scoreline_history,
    expected_goals,
    scoreline_distribution,
)


def _db(path: Path, rows: list[tuple[str, int, str, str, str, int, int, str]]) -> Path:
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
                fthg INTEGER NOT NULL,
                ftag INTEGER NOT NULL,
                ftr TEXT NOT NULL,
                raw_json TEXT NOT NULL
            )
            """
        )
        for row in rows:
            raw = json.dumps({"B365H": "2.20", "B365D": "3.40", "B365A": "3.30"})
            conn.execute("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (*row, raw))
        conn.commit()
    finally:
        conn.close()
    return path


def test_equal_goal_rates_give_equal_home_and_away_win_probability() -> None:
    probs, modal = scoreline_distribution(1.4, 1.4)
    assert sum(probs) == pytest.approx(1.0)
    assert probs[0] == pytest.approx(probs[2])
    assert modal[0] == modal[1]


def test_stronger_home_attack_raises_expected_home_goals() -> None:
    neutral_home = deque([ScoreGame(1.5, 1.2) for _ in range(5)], maxlen=20)
    strong_home = deque([ScoreGame(3.0, 1.2) for _ in range(5)], maxlen=20)
    neutral_away = deque([ScoreGame(1.2, 1.5) for _ in range(5)], maxlen=20)

    base_home, _ = expected_goals(
        home_history=neutral_home,
        away_history=neutral_away,
        league_home_goals=1.5,
        league_away_goals=1.2,
    )
    strong_lambda, _ = expected_goals(
        home_history=strong_home,
        away_history=neutral_away,
        league_home_goals=1.5,
        league_away_goals=1.2,
    )
    assert strong_lambda > base_home


def test_first_fixture_uses_fixed_neutral_fallbacks(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "first.sqlite",
        [("m1", 2024, "2024-08-10", "Alpha", "Bravo", 2, 1, "H")],
    )
    row = build_scoreline_history(db)[0]
    assert row.expected_home_goals == pytest.approx(FALLBACK_HOME_GOALS)
    assert row.expected_away_goals == pytest.approx(FALLBACK_AWAY_GOALS)
    assert row.home_prob + row.draw_prob + row.away_prob == pytest.approx(1.0)


def test_home_history_does_not_pollute_same_teams_away_role(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "roles.sqlite",
        [
            ("m1", 2024, "2024-08-10", "Alpha", "Bravo", 2, 1, "H"),
            ("m2", 2024, "2024-08-20", "Charlie", "Alpha", 1, 1, "D"),
        ],
    )
    rows = build_scoreline_history(db)
    # Charlie has no home history and Alpha has no away history. Therefore the
    # second fixture remains exactly at the league role means from m1 (2, 1),
    # despite Alpha's prior HOME match.
    assert rows[1].expected_home_goals == pytest.approx(2.0)
    assert rows[1].expected_away_goals == pytest.approx(1.0)


def test_same_day_results_cannot_change_same_day_score_model(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "same_day.sqlite",
        [
            ("m1", 2024, "2024-08-10", "Alpha", "Bravo", 5, 0, "H"),
            ("m2", 2024, "2024-08-10", "Charlie", "Delta", 0, 4, "A"),
        ],
    )
    rows = build_scoreline_history(db)
    assert rows[0].expected_home_goals == pytest.approx(FALLBACK_HOME_GOALS)
    assert rows[1].expected_home_goals == pytest.approx(FALLBACK_HOME_GOALS)
    assert rows[0].expected_away_goals == pytest.approx(FALLBACK_AWAY_GOALS)
    assert rows[1].expected_away_goals == pytest.approx(FALLBACK_AWAY_GOALS)
