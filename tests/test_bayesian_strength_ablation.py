from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

from football1.bayesian_strength_ablation import (
    VARIANTS,
    bayesian_map,
    variant_feature_names,
    walk_forward_bayesian_ablation,
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
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                ftr TEXT NOT NULL,
                raw_json TEXT NOT NULL
            )
            """
        )
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
        rows = []
        for season in (2022, 2023, 2024, 2025):
            for i, ((home, away), (result, hg, ag)) in enumerate(
                zip(fixtures, outcomes), start=1
            ):
                raw = {
                    "FTHG": str(hg),
                    "FTAG": str(ag),
                    "B365H": "2.20",
                    "B365D": "3.40",
                    "B365A": "3.30",
                    # Minimal legacy feature payload expected by build_feature_rows.
                    "FTR": result,
                }
                rows.append(
                    (
                        f"{season}-{i}",
                        season,
                        f"{season}-08-{9+i:02d}",
                        home,
                        away,
                        result,
                        json.dumps(raw),
                    )
                )
        conn.executemany("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    return path


def test_variant_names_append_bayesian_features() -> None:
    assert VARIANTS == (
        "legacy_baseline",
        "plus_bayesian_strength",
        "plus_bayesian_regime",
    )
    assert variant_feature_names("plus_bayesian_strength")[-2:] == (
        "bayes_expected_goal_diff",
        "bayes_latent_diff_sd",
    )
    assert variant_feature_names("plus_bayesian_regime")[-2:] == (
        "bayes_regime_diff",
        "bayes_regime_activity",
    )


def test_bayesian_map_is_pre_match_and_complete(tmp_path: Path) -> None:
    mapping = bayesian_map(_db(tmp_path / "map.sqlite"))
    assert len(mapping) == 24
    first = mapping["2022-1"]
    assert first.home_mean == 0.0
    assert first.away_mean == 0.0
    assert first.home_regime == 0.0
    assert first.away_regime == 0.0


def test_walk_forward_bayesian_ablation_runs_without_future_seasons(tmp_path: Path) -> None:
    report = walk_forward_bayesian_ablation(
        _db(tmp_path / "ablation.sqlite"), min_train_seasons=3
    )
    assert report["experiment"] == "market_anchored_dynamic_bayesian_ablation_v1"
    assert len(report["seasons"]) == 1
    season = report["seasons"][0]
    assert season["test_season_start_year"] == 2025
    assert season["train_matches"] == 18
    assert season["test_matches"] == 6
    for variant in VARIANTS:
        metrics = report["overall_variants"][variant]
        assert metrics["matches"] == 6
        assert math.isfinite(float(metrics["log_loss"]))
