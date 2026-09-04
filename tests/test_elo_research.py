from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from football1.elo_research import build_elo_research_export


def _db(path: Path) -> Path:
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
        rows = [
            ("2024-1", 2024, "2024-08-10", "Alpha", "Bravo", "H"),
            ("2024-2", 2024, "2024-08-17", "Bravo", "Alpha", "D"),
            ("2025-1", 2025, "2025-08-10", "Alpha", "Promoted", "H"),
            ("2025-2", 2025, "2025-08-11", "Bravo", "Promoted", "A"),
            ("2025-3", 2025, "2025-08-17", "Promoted", "Alpha", "D"),
            ("2025-4", 2025, "2025-08-18", "Alpha", "Bravo", "A"),
            ("2025-5", 2025, "2025-08-24", "Bravo", "Alpha", "H"),
        ]
        raw = json.dumps({"B365H": "2.20", "B365D": "3.40", "B365A": "3.30"})
        conn.executemany(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(*row, raw) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()
    return path


def test_elo_research_export_contains_latest_teams_table_and_histories(tmp_path: Path) -> None:
    report = build_elo_research_export(_db(tmp_path / "elo_research.sqlite"))

    assert report["schema_version"] == 1
    assert report["latest_season_start_year"] == 2025
    assert report["product_status"] == "CONTEXT_ONLY"

    ratings = report["current_ratings"]
    assert {row["team"] for row in ratings} == {"Alpha", "Bravo", "Promoted"}
    assert [row["rank"] for row in ratings] == [1, 2, 3]
    assert all("change_5_matches" in row for row in ratings)
    assert all("season_change" in row for row in ratings)

    histories = report["histories"]
    assert histories["Alpha"]
    assert histories["Bravo"]
    assert histories["Promoted"]
    assert histories["Promoted"][0]["rating"] == 1500.0


def test_elo_research_keeps_current_season_detail_and_samples_older_months(tmp_path: Path) -> None:
    report = build_elo_research_export(_db(tmp_path / "elo_research.sqlite"))
    alpha = report["histories"]["Alpha"]

    older = [point for point in alpha if point["season_start_year"] == 2024]
    current = [point for point in alpha if point["season_start_year"] == 2025]

    # Both 2024 Alpha matches fall in August, so the mobile export keeps the
    # final exact pre-match snapshot for that older month.
    assert len(older) == 1
    assert older[0]["date"] == "2024-08-17"

    # Current-season points are not thinned, preserving the recent trajectory.
    assert [point["date"] for point in current] == [
        "2025-08-10",
        "2025-08-17",
        "2025-08-18",
        "2025-08-24",
    ]
