from __future__ import annotations

from football1.features import FEATURE_NAMES, FeatureRow, feature_vector
from football1.home_away import FEATURE_NAMES as VENUE_FEATURE_NAMES
from football1.home_away import HomeAwayRow
from football1.home_away_ablation import (
    BASELINE,
    PLUS_VENUE,
    variant_feature_names,
    variant_vector,
)


def _feature_row() -> FeatureRow:
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


def _venue_row() -> HomeAwayRow:
    return HomeAwayRow(
        match_id="m1",
        season_start_year=2025,
        match_date="2025-08-10",
        home_team="Alpha",
        away_team="Bravo",
        result="H",
        venue_ppg5_diff=0.4,
        venue_gd5_diff=0.6,
        venue_ppg10_diff=0.3,
        venue_gd10_diff=0.5,
        market_probs=(0.45, 0.28, 0.27),
    )


def test_baseline_reproduces_original_feature_vector_exactly() -> None:
    row = _feature_row()
    assert variant_feature_names(BASELINE) == FEATURE_NAMES
    assert variant_vector(row, BASELINE, {}) == feature_vector(row)


def test_plus_venue_appends_exactly_four_features() -> None:
    row = _feature_row()
    venue = _venue_row()
    names = variant_feature_names(PLUS_VENUE)
    values = variant_vector(row, PLUS_VENUE, {"m1": venue})

    assert names[: len(FEATURE_NAMES)] == FEATURE_NAMES
    assert names[len(FEATURE_NAMES) :] == tuple(
        f"home_away__{name}" for name in VENUE_FEATURE_NAMES
    )
    assert values[: len(FEATURE_NAMES)] == feature_vector(row)
    assert values[-4:] == [0.4, 0.6, 0.3, 0.5]
