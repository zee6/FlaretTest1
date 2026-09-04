import numpy as np
import pytest
from sklearn.preprocessing import StandardScaler

from football1.features import FEATURE_NAMES, FeatureRow, feature_vector
from football1.offset_slant import OffsetSlantModel, _market_probs, fit_offset_slant


def _row(result: str = "H") -> FeatureRow:
    return FeatureRow(
        match_id=f"m-{result}",
        season_start_year=2025,
        match_date="2025-08-01",
        home_team="A",
        away_team="B",
        result=result,
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


def test_zero_residual_adjustment_exactly_reproduces_market():
    row = _row()
    x = np.asarray([feature_vector(row), feature_vector(row)], dtype=float)
    scaler = StandardScaler().fit(x)
    zeros = np.zeros(len(FEATURE_NAMES), dtype=float)
    model = OffsetSlantModel(
        scaler=scaler,
        intercept_h=0.0,
        intercept_a=0.0,
        coef_h=zeros,
        coef_a=zeros.copy(),
        alpha=0.1,
    )
    assert model.predict(row) == pytest.approx(_market_probs(row), abs=1e-12)


def test_offset_slant_requires_positive_regularization():
    with pytest.raises(ValueError, match="alpha must be positive"):
        fit_offset_slant([_row("H"), _row("D"), _row("A")], alpha=0.0)
