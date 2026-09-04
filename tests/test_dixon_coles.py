from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

from football1.dixon_coles import (
    DixonColesModel,
    dc_tau,
    expected_goals,
    fit_dixon_coles,
    load_matches,
    scoreline_distribution,
    walk_forward_dixon_coles,
)
from football1.dixon_coles_ablation import dixon_coles_feature_map


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
            ("Alpha", "Delta", 1, 0, "H"),
            ("Bravo", "Charlie", 2, 2, "D"),
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


def test_tau_changes_only_low_scores() -> None:
    lam, mu, rho = 1.5, 1.1, -0.08
    assert dc_tau(0, 0, lam, mu, rho) > 1.0
    assert dc_tau(1, 1, lam, mu, rho) > 1.0
    assert dc_tau(0, 1, lam, mu, rho) < 1.0
    assert dc_tau(1, 0, lam, mu, rho) < 1.0
    assert dc_tau(2, 1, lam, mu, rho) == 1.0


def test_scoreline_distribution_is_normalized() -> None:
    model = DixonColesModel(
        teams=("Alpha", "Bravo"),
        attack={"Alpha": 0.25, "Bravo": -0.25},
        defence={"Alpha": -0.15, "Bravo": 0.15},
        home_advantage=0.15,
        rho=-0.06,
        fitted_through="2025-01-01",
        time_decay_per_day=0.002,
    )
    probs, modal, lambdas = scoreline_distribution(model, "Alpha", "Bravo")
    assert math.isclose(sum(probs), 1.0, rel_tol=1e-10)
    assert all(0.0 <= p <= 1.0 for p in probs)
    assert modal[2] > 0.0
    assert lambdas[0] > lambdas[1]


def test_fit_learns_stronger_alpha(tmp_path: Path) -> None:
    matches = load_matches(_db(tmp_path / "dc.sqlite"))
    model = fit_dixon_coles(matches[:18])
    alpha_home, delta_away = expected_goals(model, "Alpha", "Delta")
    assert alpha_home > delta_away
    assert -0.20 <= model.rho <= 0.20


def test_walk_forward_is_season_strict(tmp_path: Path) -> None:
    report = walk_forward_dixon_coles(_db(tmp_path / "wf.sqlite"), min_train_seasons=3)
    assert report["model"] == "dixon_coles_v1"
    assert len(report["seasons"]) == 1
    season = report["seasons"][0]
    assert season["test_season_start_year"] == 2025
    assert season["train_matches"] == 18
    assert season["test_matches"] == 6
    assert report["overall_model"]["matches"] == 6
    assert math.isfinite(float(report["overall_model"]["log_loss"]))


def test_ablation_feature_map_uses_only_prior_seasons(tmp_path: Path) -> None:
    mapping = dixon_coles_feature_map(_db(tmp_path / "map.sqlite"))
    assert "2022-1" not in mapping
    assert "2023-1" in mapping
    assert "2025-6" in mapping
    assert mapping["2023-1"].season_start_year == 2023
