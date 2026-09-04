from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

from football1.davidson import fit_davidson, load_matches, predict_probs, walk_forward_davidson
from football1.davidson_ablation import build_leakage_safe_davidson_map
from football1.nontransitive import cycle_audit, pair_residuals


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
        fixtures = (
            ("Alpha", "Bravo", "H", 2, 0),
            ("Charlie", "Delta", "D", 1, 1),
            ("Alpha", "Charlie", "A", 0, 1),
            ("Bravo", "Delta", "H", 2, 1),
            ("Alpha", "Delta", "D", 0, 0),
            ("Bravo", "Charlie", "A", 1, 2),
        )
        rows = []
        for season in (2022, 2023, 2024, 2025):
            for i, (home, away, result, hg, ag) in enumerate(fixtures, start=1):
                raw = {
                    "FTHG": str(hg), "FTAG": str(ag), "FTR": result,
                    "B365H": "2.20", "B365D": "3.40", "B365A": "3.30",
                    "HS": "12", "AS": "10", "HST": "5", "AST": "4",
                }
                rows.append((
                    f"{season}-{i}", season, f"{season}-08-{9+i:02d}", None,
                    home, away, hg, ag, result, json.dumps(raw),
                ))
        conn.executemany("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    return path


def test_davidson_probabilities_are_three_way_and_normalized(tmp_path: Path) -> None:
    db = _db(tmp_path / "davidson.sqlite")
    matches = load_matches(db)
    model = fit_davidson(matches[:18], time_decay_per_day=0.0)
    probs = predict_probs(model, "Alpha", "Bravo")
    assert len(probs) == 3
    assert all(0.0 < p < 1.0 for p in probs)
    assert math.isclose(sum(probs), 1.0, rel_tol=0.0, abs_tol=1e-12)
    assert model.skill.keys() == {"Alpha", "Bravo", "Charlie", "Delta"}


def test_davidson_walk_forward_never_uses_test_season(tmp_path: Path) -> None:
    report = walk_forward_davidson(_db(tmp_path / "wf.sqlite"), min_train_seasons=3)
    assert report["model"] == "time_weighted_davidson_v1"
    assert len(report["seasons"]) == 1
    season = report["seasons"][0]
    assert season["test_season_start_year"] == 2025
    assert season["train_matches"] == 18
    assert season["test_matches"] == 6
    assert math.isfinite(float(report["overall_model"]["log_loss"]))


def test_davidson_feature_map_is_leakage_safe_by_season(tmp_path: Path) -> None:
    db = _db(tmp_path / "map.sqlite")
    mapping = build_leakage_safe_davidson_map(db)
    assert len(mapping) == 24
    assert mapping["2022-1"][2] == 0.0
    assert mapping["2023-1"][2] == 1.0
    assert int(mapping["2025-1"][3]) == 2025


def test_nontransitive_cycle_detector_finds_rock_paper_scissors() -> None:
    rows = [
        {"team_a": "A", "team_b": "B", "meetings": 8, "shrunk_residual_a_minus_b": 0.10},
        {"team_a": "B", "team_b": "C", "meetings": 8, "shrunk_residual_a_minus_b": 0.09},
        {"team_a": "A", "team_b": "C", "meetings": 8, "shrunk_residual_a_minus_b": -0.08},
    ]
    audit = cycle_audit(rows)
    assert audit["complete_significant_triangles"] == 1
    assert audit["cyclic_triangles"] == 1
    assert audit["transitive_triangles"] == 0


def test_pair_residuals_are_antisymmetric_by_construction(tmp_path: Path) -> None:
    matches = load_matches(_db(tmp_path / "pairs.sqlite"))
    rows = pair_residuals(matches)
    assert rows
    for row in rows:
        assert str(row["team_a"]) < str(row["team_b"])
        assert math.isfinite(float(row["shrunk_residual_a_minus_b"]))
