from __future__ import annotations

import pytest

from football1.features import FeatureRow
from football1.market_regime_audit import favorite_price_regime, favorite_selection


def _row(*, home: float, draw: float, away: float) -> FeatureRow:
    return FeatureRow(
        match_id="x",
        season_start_year=2025,
        match_date="2026-01-01",
        home_team="Home",
        away_team="Away",
        result="H",
        elo_diff=0.0,
        ppg5_diff=0.0,
        gf5_diff=0.0,
        ga5_diff=0.0,
        shots5_diff=0.0,
        shots_allowed5_diff=0.0,
        sot5_diff=0.0,
        sot_allowed5_diff=0.0,
        ppg10_diff=0.0,
        gf10_diff=0.0,
        ga10_diff=0.0,
        rest_days_diff=0.0,
        log_prior_games_home=0.0,
        log_prior_games_away=0.0,
        b365_home=home,
        b365_draw=draw,
        b365_away=away,
    )


def test_favorite_price_regime_boundaries_are_frozen() -> None:
    assert favorite_price_regime(1.49) == "very_short"
    assert favorite_price_regime(1.50) == "short"
    assert favorite_price_regime(1.79) == "short"
    assert favorite_price_regime(1.80) == "moderate"
    assert favorite_price_regime(2.20) == "moderate"
    assert favorite_price_regime(2.21) == "open"


def test_favorite_price_regime_rejects_invalid_decimal_odds() -> None:
    with pytest.raises(ValueError):
        favorite_price_regime(1.0)


def test_favorite_selection_uses_shortest_b365_price() -> None:
    index, odds, label = favorite_selection(_row(home=2.40, draw=3.30, away=1.72))
    assert index == 2
    assert odds == pytest.approx(1.72)
    assert label == "A"


def test_favorite_selection_requires_complete_market() -> None:
    row = _row(home=2.00, draw=3.30, away=4.00)
    row = FeatureRow(**{**row.__dict__, "b365_draw": None})
    with pytest.raises(ValueError):
        favorite_selection(row)
