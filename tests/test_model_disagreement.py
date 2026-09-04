from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

from football1.model_disagreement import (
    _blend,
    _mean_probs,
    build_disagreement_rows,
    model_disagreement_audit,
)


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


def test_mean_and_blend_are_probabilities() -> None:
    mean = _mean_probs(
        [(0.60, 0.25, 0.15), (0.50, 0.30, 0.20), (0.55, 0.25, 0.20)]
    )
    assert math.isclose(sum(mean), 1.0, rel_tol=1e-12)
    blend = _blend((0.52, 0.28, 0.20), mean)
    assert math.isclose(sum(blend), 1.0, rel_tol=1e-12)
    assert blend[0] > blend[2]


def test_disagreement_rows_are_strict_oos(tmp_path: Path) -> None:
    rows = build_disagreement_rows(
        _db(tmp_path / "observer.sqlite"), min_train_seasons=3
    )
    assert len(rows) == 6
    assert {row.season_start_year for row in rows} == {2025}
    assert all(set(row.shadow_probs) == {"elo", "bayesian_strength", "poisson", "dixon_coles"} for row in rows)
    assert all(0 <= row.market_alignment_count <= 4 for row in rows)
    assert all(1 <= row.shadow_consensus_count <= 4 for row in rows)


def test_audit_keeps_agreement_as_observer_only(tmp_path: Path) -> None:
    report = model_disagreement_audit(
        _db(tmp_path / "audit.sqlite"), min_train_seasons=3
    )
    assert report["status"] == "observer_only_zero_decision_weight"
    assert report["groups"]["all_oos"]["matches"] == 6
    assert report["groups"]["all_oos"]["market"]["matches"] == 6
    assert len(report["seasons"]) == 1
