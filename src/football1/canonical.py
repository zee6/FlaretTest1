from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from football1.schema import classify_column


REQUIRED_COLUMNS = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}


@dataclass(frozen=True)
class CanonicalMatch:
    match_id: str
    season_start_year: int
    match_date: str
    kickoff_time: str | None
    home_team: str
    away_team: str
    fthg: int
    ftag: int
    ftr: str
    hthg: int | None
    htag: int | None
    htr: str | None
    source_file: str
    source_row_number: int
    raw_json: str


def parse_match_date(value: str) -> str:
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Unsupported match date format: {value!r}")


def _optional_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value)


def _result_from_goals(home: int, away: int) -> str:
    if home > away:
        return "H"
    if home < away:
        return "A"
    return "D"


def _match_id(season_start_year: int, date: str, home: str, away: str) -> str:
    key = f"EPL|{season_start_year}|{date}|{home.strip()}|{away.strip()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def read_canonical_matches(path: Path, season_start_year: int) -> list[CanonicalMatch]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no CSV header")

        missing = REQUIRED_COLUMNS.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"{path} missing required columns: {sorted(missing)}")

        rows: list[CanonicalMatch] = []
        for row_number, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue

            match_date = parse_match_date(row["Date"])
            home = row["HomeTeam"].strip()
            away = row["AwayTeam"].strip()
            fthg = int(row["FTHG"])
            ftag = int(row["FTAG"])
            ftr = row["FTR"].strip()

            expected = _result_from_goals(fthg, ftag)
            if ftr != expected:
                raise ValueError(
                    f"{path}:{row_number} result mismatch: FTHG={fthg}, "
                    f"FTAG={ftag}, FTR={ftr!r}, expected {expected!r}"
                )

            kickoff = (row.get("Time") or "").strip() or None
            hthg = _optional_int(row.get("HTHG"))
            htag = _optional_int(row.get("HTAG"))
            htr = (row.get("HTR") or "").strip() or None

            if hthg is not None and htag is not None and htr is not None:
                expected_half = _result_from_goals(hthg, htag)
                if htr != expected_half:
                    raise ValueError(
                        f"{path}:{row_number} half-time result mismatch: "
                        f"HTHG={hthg}, HTAG={htag}, HTR={htr!r}, "
                        f"expected {expected_half!r}"
                    )

            rows.append(
                CanonicalMatch(
                    match_id=_match_id(season_start_year, match_date, home, away),
                    season_start_year=season_start_year,
                    match_date=match_date,
                    kickoff_time=kickoff,
                    home_team=home,
                    away_team=away,
                    fthg=fthg,
                    ftag=ftag,
                    ftr=ftr,
                    hthg=hthg,
                    htag=htag,
                    htr=htr,
                    source_file=path.name,
                    source_row_number=row_number,
                    raw_json=json.dumps(row, sort_keys=True, ensure_ascii=False),
                )
            )
        return rows


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,
            season_start_year INTEGER NOT NULL,
            match_date TEXT NOT NULL,
            kickoff_time TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            fthg INTEGER NOT NULL,
            ftag INTEGER NOT NULL,
            ftr TEXT NOT NULL CHECK (ftr IN ('H','D','A')),
            hthg INTEGER,
            htag INTEGER,
            htr TEXT CHECK (htr IS NULL OR htr IN ('H','D','A')),
            source_file TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            raw_json TEXT NOT NULL,
            UNIQUE (season_start_year, match_date, home_team, away_team)
        );

        CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
        CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team);

        CREATE TABLE IF NOT EXISTS schema_inventory (
            source_file TEXT NOT NULL,
            season_start_year INTEGER NOT NULL,
            ordinal INTEGER NOT NULL,
            column_name TEXT NOT NULL,
            availability_class TEXT NOT NULL,
            PRIMARY KEY (source_file, column_name)
        );
        """
    )


def build_database(
    season_files: Iterable[tuple[int, Path]],
    output_path: Path,
) -> dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(output_path)
    try:
        _create_schema(conn)
        inserted = 0
        files = 0
        for season_start_year, path in season_files:
            files += 1
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.reader(fh)
                try:
                    header = next(reader)
                except StopIteration as exc:
                    raise ValueError(f"{path} has no CSV header") from exc

            for ordinal, name in enumerate(header):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO schema_inventory
                        (source_file, season_start_year, ordinal, column_name, availability_class)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (path.name, season_start_year, ordinal, name, classify_column(name).value),
                )

            for match in read_canonical_matches(path, season_start_year):
                try:
                    conn.execute(
                        """
                        INSERT INTO matches (
                            match_id, season_start_year, match_date, kickoff_time,
                            home_team, away_team, fthg, ftag, ftr,
                            hthg, htag, htr, source_file, source_row_number, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            match.match_id,
                            match.season_start_year,
                            match.match_date,
                            match.kickoff_time,
                            match.home_team,
                            match.away_team,
                            match.fthg,
                            match.ftag,
                            match.ftr,
                            match.hthg,
                            match.htag,
                            match.htr,
                            match.source_file,
                            match.source_row_number,
                            match.raw_json,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ValueError(
                        f"Duplicate or conflicting match while importing {path}: "
                        f"{match.match_date} {match.home_team} v {match.away_team}"
                    ) from exc
                inserted += 1
        conn.commit()
        return {"files": files, "matches": inserted}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
