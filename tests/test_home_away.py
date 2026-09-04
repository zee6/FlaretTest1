from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from football1.home_away import build_home_away_rows


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


def test_home_result_updates_future_home_profile(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "home.sqlite",
        [
            ("m1", 2024, "2024-08-10", "Alpha", "Bravo", 2, 0, "H"),
            ("m2", 2024, "2024-08-20", "Alpha", "Charlie", 1, 0, "H"),
        ],
    )
    rows = build_home_away_rows(db)
    assert rows[0].venue_ppg5_diff == pytest.approx(0.0)
    assert rows[1].venue_ppg5_diff > 0.0
    assert rows[1].venue_gd5_diff > 0.0


def test_home_result_does_not_pollute_away_profile(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "separate.sqlite",
        [
            ("m1", 2024, "2024-08-10", "Alpha", "Bravo", 3, 0, "H"),
            ("m2", 2024, "2024-08-20", "Charlie", "Alpha", 1, 1, "D"),
        ],
    )
    rows = build_home_away_rows(db)
    # Charlie has no prior home matches and Alpha has no prior away matches,
    # so both sides are still on the same neutral venue prior.
    assert rows[1].venue_ppg5_diff == pytest.approx(0.0)
    assert rows[1].venue_gd5_diff == pytest.approx(0.0)


def test_same_day_results_cannot_change_same_day_features(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "same_day.sqlite",
        [
            ("m1", 2024, "2024-08-10", "Alpha", "Bravo", 2, 0, "H"),
            ("m2", 2024, "2024-08-10", "Alpha", "Charlie", 2, 0, "H"),
        ],
    )
    rows = build_home_away_rows(db)
    assert rows[0].venue_ppg5_diff == pytest.approx(0.0)
    assert rows[1].venue_ppg5_diff == pytest.approx(0.0)
    assert rows[1].venue_gd5_diff == pytest.approx(0.0)
