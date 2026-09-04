import json
import sqlite3
from pathlib import Path

import pytest

from football1.features import FEATURE_NAMES, build_feature_rows, feature_vector


def _make_matches_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE matches (
                match_id TEXT PRIMARY KEY,
                season_start_year INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                kickoff_time TEXT,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                fthg INTEGER NOT NULL,
                ftag INTEGER NOT NULL,
                ftr TEXT NOT NULL,
                raw_json TEXT NOT NULL
            )
            """
        )
        rows = [
            ("m1", 2025, "2025-08-01", None, "A", "B", 2, 0, "H", {"HS": "10", "AS": "7", "HST": "5", "AST": "2", "B365H": "2", "B365D": "3.5", "B365A": "4"}),
            # Synthetic same-day repeat for A: feature construction must not see m1.
            ("m2", 2025, "2025-08-01", None, "A", "C", 0, 1, "A", {"HS": "8", "AS": "9", "HST": "3", "AST": "4", "B365H": "2.2", "B365D": "3.4", "B365A": "3.5"}),
            ("m3", 2025, "2025-08-08", None, "A", "D", 1, 1, "D", {"HS": "11", "AS": "10", "HST": "4", "AST": "4", "B365H": "2.1", "B365D": "3.3", "B365A": "3.8"}),
        ]
        for row in rows:
            conn.execute(
                "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*row[:-1], json.dumps(row[-1])),
            )
        conn.commit()
    finally:
        conn.close()


def test_same_day_results_do_not_leak_into_features(tmp_path: Path):
    db = tmp_path / "matches.sqlite"
    _make_matches_db(db)
    rows = {row.match_id: row for row in build_feature_rows(db)}

    # Both same-day A fixtures were snapshotted before either result was applied.
    assert rows["m1"].log_prior_games_home == pytest.approx(0.0)
    assert rows["m2"].log_prior_games_home == pytest.approx(0.0)

    # A's next-date fixture sees both completed prior matches.
    assert rows["m3"].log_prior_games_home == pytest.approx(__import__("math").log1p(2))
    assert rows["m3"].elo_diff != pytest.approx(0.0)


def test_feature_vector_contains_no_bookmaker_odds(tmp_path: Path):
    db = tmp_path / "matches.sqlite"
    _make_matches_db(db)
    row = build_feature_rows(db)[0]
    vector = feature_vector(row)
    assert len(vector) == len(FEATURE_NAMES)
    assert not any("b365" in name.lower() or "odds" in name.lower() for name in FEATURE_NAMES)
    assert row.b365_home == pytest.approx(2.0)  # retained only for paired evaluation
