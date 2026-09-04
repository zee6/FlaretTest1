from __future__ import annotations

from football1.elo_ablation import NON_ELO_FEATURE_NAMES, variant_feature_names, variant_vector
from football1.features import FEATURE_NAMES, FeatureRow


def _row() -> FeatureRow:
    return FeatureRow(
        match_id="m1",
        season_start_year=2025,
        match_date="2025-08-10",
        home_team="Alpha",
        away_team="Bravo",
        result="H",
        elo_diff=42.0,
        ppg5_diff=0.1,
        gf5_diff=0.2,
        ga5_diff=-0.1,
        shots5_diff=1.0,
        shots_allowed5_diff=-1.0,
        sot5_diff=0.5,
        sot_allowed5_diff=-0.5,
        ppg10_diff=0.15,
        gf10_diff=0.25,
        ga10_diff=-0.15,
        rest_days_diff=2.0,
        log_prior_games_home=3.0,
        log_prior_games_away=2.5,
        b365_home=2.1,
        b365_draw=3.4,
        b365_away=3.6,
    )


def test_no_elo_variant_removes_only_legacy_elo() -> None:
    row = _row()
    vector = variant_vector(row, "no_elo", {})
    assert len(vector) == len(FEATURE_NAMES) - 1
    assert variant_feature_names("no_elo") == NON_ELO_FEATURE_NAMES
    assert "elo_diff" not in variant_feature_names("no_elo")


def test_legacy_variant_reproduces_original_feature_order() -> None:
    row = _row()
    vector = variant_vector(row, "legacy_elo", {})
    assert len(vector) == len(FEATURE_NAMES)
    assert variant_feature_names("legacy_elo") == FEATURE_NAMES
    assert vector[0] == 42.0


def test_modular_variant_replaces_instead_of_duplicates_elo() -> None:
    row = _row()
    vector = variant_vector(row, "modular_elo_v1", {"m1": 87.0})
    names = variant_feature_names("modular_elo_v1")
    assert len(vector) == len(FEATURE_NAMES)
    assert "elo_diff" not in names
    assert names[-1] == "modular_elo_strength_diff"
    assert vector[-1] == 87.0
