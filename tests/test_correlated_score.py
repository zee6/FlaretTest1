from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

from football1.correlated_score import (
    COMMON_FRACTION_MAX,
    FRAILTY_K_MAX,
    FRAILTY_K_MIN,
    bivariate_poisson_logpmf,
    bivariate_probabilities,
    fit_dependence,
    frailty_probabilities,
    gamma_frailty_logpmf,
    load_actual_scores,
    season_start_prediction_map,
    walk_forward_correlated_score,
)
from football1.scoreline import build_scoreline_history, scoreline_distribution


def _db(path: Path) -> Path:
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
        fixtures = [
            ("Alpha", "Bravo", 2, 0, "H"),
            ("Charlie", "Delta", 1, 1, "D"),
            ("Alpha", "Charlie", 3, 1, "H"),
            ("Bravo", "Delta", 0, 1, "A"),
            ("Alpha", "Delta", 2, 2, "D"),
            ("Bravo", "Charlie", 1, 1, "D"),
        ]
        rows = []
        for season in (2022, 2023, 2024, 2025):
            for i, (home, away, hg, ag, result) in enumerate(fixtures, start=1):
                raw = {
                    "FTHG": str(hg),
                    "FTAG": str(ag),
                    "FTR": result,
                    "B365H": "2.20",
                    "B365D": "3.40",
                    "B365A": "3.30",
                }
                rows.append(
                    (
                        f"{season}-{i}",
                        season,
                        f"{season}-08-{9+i:02d}",
                        None,
                        home,
                        away,
                        hg,
                        ag,
                        result,
                        json.dumps(raw),
                    )
                )
        conn.executemany("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    return path


def test_bivariate_zero_common_matches_independent() -> None:
    lambda_home, lambda_away = 1.55, 1.15
    probs = bivariate_probabilities(lambda_home, lambda_away, 0.0)
    independent, _ = scoreline_distribution(lambda_home, lambda_away, max_score=12)
    for actual, expected in zip(probs, independent):
        assert math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10)


def test_joint_logpmfs_are_finite() -> None:
    assert math.isfinite(bivariate_poisson_logpmf(2, 1, 1.7, 1.2, 0.2))
    assert math.isfinite(gamma_frailty_logpmf(2, 1, 1.7, 1.2, 3.0))


def test_frailty_large_k_approaches_independent() -> None:
    lambda_home, lambda_away = 1.4, 1.1
    frailty = frailty_probabilities(lambda_home, lambda_away, FRAILTY_K_MAX)
    independent, _ = scoreline_distribution(lambda_home, lambda_away, max_score=12)
    for actual, expected in zip(frailty, independent):
        assert abs(actual - expected) < 0.002


def test_fit_dependence_respects_frozen_bounds(tmp_path: Path) -> None:
    db = _db(tmp_path / "dependence.sqlite")
    rows = build_scoreline_history(db)
    fit = fit_dependence(rows[:18], load_actual_scores(db))
    assert 0.0 <= fit.common_fraction <= COMMON_FRACTION_MAX
    assert FRAILTY_K_MIN <= fit.frailty_k <= FRAILTY_K_MAX
    assert fit.train_matches == 18


def test_season_start_map_uses_only_earlier_seasons(tmp_path: Path) -> None:
    mapping = season_start_prediction_map(_db(tmp_path / "map.sqlite"))
    assert "2022-1" not in mapping
    assert "2023-1" in mapping
    assert "2025-6" in mapping
    assert mapping["2023-1"].season_start_year == 2023


def test_walk_forward_report_is_strict(tmp_path: Path) -> None:
    report = walk_forward_correlated_score(
        _db(tmp_path / "wf.sqlite"), min_train_seasons=3
    )
    assert report["experiment"] == "correlated_score_models_v1"
    assert len(report["seasons"]) == 1
    season = report["seasons"][0]
    assert season["test_season_start_year"] == 2025
    assert season["train_matches"] == 18
    assert season["test_matches"] == 6
    assert report["overall"]["bivariate_poisson"]["matches"] == 6
    assert math.isfinite(float(report["overall"]["gamma_frailty"]["log_loss"]))
