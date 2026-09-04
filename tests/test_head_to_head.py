from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from football1.head_to_head import build_head_to_head_history


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


def test_first_meeting_is_neutral(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "first.sqlite",
        [("m1", 2024, "2024-08-10", "Alpha", "Bravo", 2, 1, "H")],
    )
    row = build_head_to_head_history(db)[0]
    assert row.pair_score_edge == pytest.approx(0.0)
    assert row.pair_goal_diff == pytest.approx(0.0)
    assert row.same_venue_score_edge == pytest.approx(0.0)
    assert row.pair_history_strength == pytest.approx(0.0)


def test_prior_win_moves_future_pair_signal_but_is_shrunk(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "repeat.sqlite",
        [
            ("m1", 2024, "2024-08-10", "Alpha", "Bravo", 3, 0, "H"),
            ("m2", 2024, "2025-01-10", "Alpha", "Bravo", 1, 0, "H"),
        ],
    )
    rows = build_head_to_head_history(db)
    assert 0.0 < rows[1].pair_score_edge < 0.5
    assert rows[1].pair_goal_diff > 0.0
    assert 0.0 < rows[1].same_venue_score_edge < 0.5
    assert 0.0 < rows[1].pair_history_strength < 1.0


def test_reverse_fixture_flips_pair_perspective_and_resets_same_venue(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "reverse.sqlite",
        [
            ("m1", 2024, "2024-08-10", "Alpha", "Bravo", 2, 0, "H"),
            ("m2", 2024, "2025-01-10", "Bravo", "Alpha", 1, 1, "D"),
        ],
    )
    rows = build_head_to_head_history(db)
    # From Bravo's perspective the prior match was a loss.
    assert rows[1].pair_score_edge < 0.0
    assert rows[1].pair_goal_diff < 0.0
    # No prior Bravo-home / Alpha-away meeting exists.
    assert rows[1].same_venue_score_edge == pytest.approx(0.0)
    assert rows[1].same_venue_history_strength == pytest.approx(0.0)


def test_same_day_result_cannot_enter_same_day_h2h(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "same_day.sqlite",
        [
            ("m1", 2024, "2024-08-10", "Alpha", "Bravo", 2, 0, "H"),
            ("m2", 2024, "2024-08-10", "Bravo", "Alpha", 0, 2, "A"),
        ],
    )
    rows = build_head_to_head_history(db)
    assert rows[0].pair_history_strength == pytest.approx(0.0)
    assert rows[1].pair_history_strength == pytest.approx(0.0)
    assert rows[1].pair_score_edge == pytest.approx(0.0)
