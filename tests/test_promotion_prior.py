from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from football1.elo import build_elo_rows
from football1.promotion_prior import (
    CohortSample,
    build_promotion_prior_history,
    empirical_promoted_prior,
    entrants_by_season,
)


def _make_db(path: Path, rows: list[tuple[str, int, str, str, str, str]]) -> None:
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
        raw = json.dumps({"B365H": "2.00", "B365D": "3.40", "B365A": "3.80"})
        conn.executemany(
            """
            INSERT INTO matches (
                match_id, season_start_year, match_date,
                home_team, away_team, ftr, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row, raw) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


def test_empirical_promoted_prior_falls_back_until_minimum_sample_count() -> None:
    samples = [
        CohortSample(2020, "A", 1460.0),
        CohortSample(2020, "B", 1480.0),
    ]
    assert empirical_promoted_prior(samples, min_samples=3) == 1500.0
    assert empirical_promoted_prior(samples, min_samples=2) == pytest.approx(1470.0)
    with pytest.raises(ValueError):
        empirical_promoted_prior(samples, min_samples=0)


def test_entrants_are_relative_to_immediately_previous_season() -> None:
    records: list[tuple[object, ...]] = [
        ("m1", 2020, "2020-08-01", "A", "B", "H", "{}"),
        ("m2", 2021, "2021-08-01", "A", "C", "H", "{}"),
        ("m3", 2022, "2022-08-01", "A", "B", "H", "{}"),
    ]
    entrants = entrants_by_season(records)
    assert entrants[2020] == set()
    assert entrants[2021] == {"C"}
    assert entrants[2022] == {"B"}


def test_returner_keeps_epl_history_but_first_time_team_gets_prior(tmp_path: Path) -> None:
    db = tmp_path / "football.sqlite"
    _make_db(
        db,
        [
            ("s20", 2020, "2020-08-01", "A", "B", "H"),
            ("s21", 2021, "2021-08-01", "A", "C", "H"),
            ("s22", 2022, "2022-08-01", "A", "B", "H"),
            ("s23", 2023, "2023-08-01", "A", "D", "H"),
        ],
    )

    history = build_promotion_prior_history(db, min_cohort_samples=1)
    policy = {row["season_start_year"]: row for row in history["season_policy"]}

    assert policy[2021]["first_time_archive_entrants"] == ["C"]
    assert policy[2022]["returning_entrants"] == ["B"]
    assert policy[2022]["first_time_archive_entrants"] == []
    assert policy[2023]["first_time_archive_entrants"] == ["D"]
    assert policy[2023]["prior_sample_count"] == 2
    assert policy[2023]["prior_source_seasons"] == [2021, 2022]
    assert policy[2023]["empirical_prior_rating"] < 1500.0

    baseline = {row.match_id: row for row in history["baseline_rows"]}
    adjusted = {row.match_id: row for row in history["adjusted_rows"]}

    # Returning B retains its decayed historical EPL rating, so the promotion
    # prior does not overwrite known evidence.
    assert adjusted["s22"].away_rating == pytest.approx(baseline["s22"].away_rating)

    # First-time D has no EPL evidence and therefore receives the historical
    # promoted cohort prior rather than neutral 1500.
    assert baseline["s23"].away_rating == pytest.approx(1500.0)
    assert adjusted["s23"].away_rating == pytest.approx(policy[2023]["empirical_prior_rating"])


def test_parallel_baseline_matches_existing_elo_policy(tmp_path: Path) -> None:
    db = tmp_path / "football.sqlite"
    _make_db(
        db,
        [
            ("m1", 2020, "2020-08-01", "A", "B", "H"),
            ("m2", 2020, "2020-08-08", "B", "A", "D"),
            ("m3", 2021, "2021-08-01", "A", "C", "A"),
            ("m4", 2021, "2021-08-08", "C", "A", "D"),
            ("m5", 2022, "2022-08-01", "A", "B", "H"),
        ],
    )

    history = build_promotion_prior_history(db, min_cohort_samples=1)
    parallel = {row.match_id: row for row in history["baseline_rows"]}
    existing = {row.match_id: row for row in build_elo_rows(db)}

    assert parallel.keys() == existing.keys()
    for match_id in parallel:
        assert parallel[match_id].home_rating == pytest.approx(existing[match_id].home_rating)
        assert parallel[match_id].away_rating == pytest.approx(existing[match_id].away_rating)
        assert parallel[match_id].elo_diff == pytest.approx(existing[match_id].elo_diff)
