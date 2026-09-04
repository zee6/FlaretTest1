import csv
import sqlite3
from pathlib import Path

import pytest

from football1.canonical import build_database, parse_match_date, read_canonical_matches


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_parse_match_date_supports_long_and_short_years():
    assert parse_match_date("15/08/2026") == "2026-08-15"
    assert parse_match_date("15/08/26") == "2026-08-15"


def test_rejects_result_inconsistent_with_goals(tmp_path: Path):
    path = tmp_path / "bad.csv"
    _write_csv(
        path,
        ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"],
        [{"Date": "15/08/2026", "HomeTeam": "A", "AwayTeam": "B", "FTHG": 2, "FTAG": 1, "FTR": "D"}],
    )
    with pytest.raises(ValueError, match="result mismatch"):
        read_canonical_matches(path, 2026)


def test_database_records_schema_drift_and_matches(tmp_path: Path):
    p1 = tmp_path / "EPL_2526_E0.csv"
    p2 = tmp_path / "EPL_2627_E0.csv"

    _write_csv(
        p1,
        ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A"],
        [{"Date": "16/08/2025", "HomeTeam": "A", "AwayTeam": "B", "FTHG": 1, "FTAG": 1, "FTR": "D", "B365H": 2.0, "B365D": 3.4, "B365A": 4.0}],
    )
    _write_csv(
        p2,
        ["Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A", "B365CH", "B365CD", "B365CA"],
        [{"Date": "15/08/2026", "Time": "15:00", "HomeTeam": "C", "AwayTeam": "D", "FTHG": 2, "FTAG": 0, "FTR": "H", "B365H": 1.8, "B365D": 3.6, "B365A": 5.0, "B365CH": 1.75, "B365CD": 3.7, "B365CA": 5.2}],
    )

    db = tmp_path / "football1.sqlite"
    result = build_database([(2025, p1), (2026, p2)], db)
    assert result == {"files": 2, "matches": 2}

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 2
        assert conn.execute(
            "SELECT availability_class FROM schema_inventory WHERE source_file=? AND column_name='B365CH'",
            (p2.name,),
        ).fetchone()[0] == "market"
    finally:
        conn.close()
