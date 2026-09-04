import math

import pytest

from football1.features import FEATURE_NAMES, FeatureRow
from football1.slant_model import (
    MARKET_CALIBRATION_FEATURE_NAMES,
    SLANT_FEATURE_NAMES,
    market_log_ratio_features,
    market_probabilities,
    slant_feature_vector,
)


def _row() -> FeatureRow:
    return FeatureRow(
        match_id="m1",
        season_start_year=2025,
        match_date="2025-08-01",
        home_team="A",
        away_team="B",
        result="H",
        elo_diff=10.0,
        ppg5_diff=0.1,
        gf5_diff=0.2,
        ga5_diff=-0.1,
        shots5_diff=1.0,
        shots_allowed5_diff=-1.0,
        sot5_diff=0.5,
        sot_allowed5_diff=-0.3,
        ppg10_diff=0.15,
        gf10_diff=0.1,
        ga10_diff=-0.2,
        rest_days_diff=2.0,
        log_prior_games_home=3.0,
        log_prior_games_away=3.1,
        b365_home=2.0,
        b365_draw=4.0,
        b365_away=4.0,
    )


def test_market_control_uses_only_two_independent_market_log_ratios():
    row = _row()
    probs = market_probabilities(row)
    assert probs == pytest.approx((0.5, 0.25, 0.25))
    features = market_log_ratio_features(row)
    assert features == pytest.approx((math.log(2.0), 0.0))
    assert tuple(MARKET_CALIBRATION_FEATURE_NAMES) == (
        "market_log_h_over_d",
        "market_log_a_over_d",
    )


def test_slant_adds_football_features_without_replacing_market_control():
    row = _row()
    vector = slant_feature_vector(row)
    assert len(vector) == 2 + len(FEATURE_NAMES)
    assert tuple(SLANT_FEATURE_NAMES[:2]) == tuple(MARKET_CALIBRATION_FEATURE_NAMES)
    assert tuple(SLANT_FEATURE_NAMES[2:]) == tuple(FEATURE_NAMES)


def test_missing_market_odds_fail_hard_instead_of_changing_sample():
    row = _row()
    missing = FeatureRow(**{**row.__dict__, "b365_home": None})
    with pytest.raises(ValueError, match="Missing Bet365"):
        market_probabilities(missing)
