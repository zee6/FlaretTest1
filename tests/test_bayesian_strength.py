from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

import numpy as np

from football1.bayesian_strength import (
    HOME_ADVANTAGE_GOALS,
    PRIOR_VARIANCE,
    _kalman_match_update,
    build_bayesian_strength_rows,
    walk_forward_bayesian_strength,
)


def _db(path: Path, rows: list[tuple[str, int, str, str, str, str, int, int]]) -> Path:
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
        payloads = []
        for match_id, season, date, home, away, result, hg, ag in rows:
            raw = json.dumps(
                {
                    "FTHG": str(hg),
                    "FTAG": str(ag),
                    "B365H": "2.20",
                    "B365D": "3.40",
                    "B365A": "3.30",
                }
            )
            payloads.append((match_id, season, date, home, away, result, raw))
        conn.executemany("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?)", payloads)
        conn.commit()
    finally:
        conn.close()
    return path


def test_kalman_win_moves_home_up_and_away_down() -> None:
    mean = np.array([0.0, 0.0])
    covariance = np.eye(2) * PRIOR_VARIANCE
    new_mean, new_cov, innovation, surprise = _kalman_match_update(
        mean,
        covariance,
        home_index=0,
        away_index=1,
        observed_goal_diff=2.0,
        home_advantage_goals=HOME_ADVANTAGE_GOALS,
        observation_variance=2.25,
    )
    assert innovation > 0
    assert surprise > 0
    assert new_mean[0] > 0
    assert new_mean[1] < 0
    assert new_cov[0, 0] < covariance[0, 0]
    assert np.allclose(new_cov, new_cov.T)


def test_same_date_states_are_frozen_before_results_update(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "same_day.sqlite",
        [
            ("m1", 2025, "2025-08-10", "Alpha", "Bravo", "H", 4, 0),
            # Synthetic double fixture is intentional: m1 must not alter the
            # second pre-match snapshot on the same date.
            ("m2", 2025, "2025-08-10", "Alpha", "Charlie", "A", 0, 1),
        ],
    )
    rows = build_bayesian_strength_rows(db)
    assert rows[0].home_mean == 0.0
    assert rows[1].home_mean == 0.0
    assert rows[1].away_mean == 0.0
    assert rows[0].home_regime == 0.0
    assert rows[1].home_regime == 0.0


def test_result_updates_next_match_and_regime_uses_only_prior_surprise(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "sequence.sqlite",
        [
            ("m1", 2025, "2025-08-10", "Alpha", "Bravo", "H", 4, 0),
            ("m2", 2025, "2025-08-17", "Alpha", "Charlie", "D", 1, 1),
        ],
    )
    rows = build_bayesian_strength_rows(db)
    first, second = rows
    assert first.home_mean == 0.0
    assert first.home_regime == 0.0
    assert second.home_mean > 0.0
    assert second.home_regime > 0.0
    assert second.expected_goal_diff > HOME_ADVANTAGE_GOALS


def test_uncertainty_grows_with_time_without_observation(tmp_path: Path) -> None:
    short = _db(
        tmp_path / "short.sqlite",
        [
            ("m1", 2025, "2025-08-10", "Alpha", "Bravo", "D", 0, 0),
            ("m2", 2025, "2025-08-11", "Alpha", "Charlie", "D", 0, 0),
        ],
    )
    long = _db(
        tmp_path / "long.sqlite",
        [
            ("m1", 2025, "2025-08-10", "Alpha", "Bravo", "D", 0, 0),
            ("m2", 2025, "2025-10-10", "Alpha", "Charlie", "D", 0, 0),
        ],
    )
    short_rows = build_bayesian_strength_rows(short)
    long_rows = build_bayesian_strength_rows(long)
    assert long_rows[1].home_sd > short_rows[1].home_sd


def test_walk_forward_reports_strength_and_regime_candidates(tmp_path: Path) -> None:
    rows: list[tuple[str, int, str, str, str, str, int, int]] = []
    fixtures = (
        ("Alpha", "Bravo"),
        ("Charlie", "Delta"),
        ("Alpha", "Charlie"),
        ("Bravo", "Delta"),
        ("Alpha", "Delta"),
        ("Bravo", "Charlie"),
    )
    outcomes = (
        ("H", 2, 0),
        ("D", 1, 1),
        ("A", 0, 1),
        ("H", 3, 1),
        ("D", 0, 0),
        ("A", 1, 2),
    )
    for season in (2022, 2023, 2024, 2025):
        for i, ((home, away), (result, hg, ag)) in enumerate(
            zip(fixtures, outcomes), start=1
        ):
            rows.append(
                (
                    f"{season}-{i}",
                    season,
                    f"{season}-08-{9+i:02d}",
                    home,
                    away,
                    result,
                    hg,
                    ag,
                )
            )

    report = walk_forward_bayesian_strength(
        _db(tmp_path / "walk.sqlite", rows), min_train_seasons=3
    )
    assert report["model"] == "dynamic_bayesian_strength_v1"
    assert report["bayesian_strength"]["overall_model"]["matches"] == 6
    assert report["bayesian_strength_plus_regime"]["overall_model"]["matches"] == 6
    assert len(report["seasons"]) == 1
    assert report["seasons"][0]["test_season_start_year"] == 2025
    assert math.isfinite(
        float(report["bayesian_strength"]["overall_model"]["log_loss"])
    )
    assert math.isfinite(
        float(
            report["bayesian_strength_plus_regime"]["overall_model"]["log_loss"]
        )
    )
