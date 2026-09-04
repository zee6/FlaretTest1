from __future__ import annotations

import pytest

from football1.features import FeatureRow
from football1.historical_closing_line import ClosingObservation
from football1.market_regime_movement import opening_favorite_closing_summary


def _row() -> FeatureRow:
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
        b365_home=1.80,
        b365_draw=3.60,
        b365_away=4.50,
    )


def test_opening_favorite_closing_summary_detects_shortening() -> None:
    obs = ClosingObservation(base=_row(), closing_odds=(1.65, 3.80, 5.00))
    summary = opening_favorite_closing_summary([obs])
    assert summary["matches"] == 1
    assert summary["fraction_opening_favorite_shortened"] == pytest.approx(1.0)
    assert float(summary["mean_opening_vs_closing_decimal_price_ratio"]) == pytest.approx(1.80 / 1.65 - 1.0)
    assert float(summary["mean_opening_favorite_probability_move"]) > 0.0


def test_opening_favorite_closing_summary_empty_is_explicit() -> None:
    summary = opening_favorite_closing_summary([])
    assert summary["matches"] == 0
    assert summary["fraction_opening_favorite_shortened"] is None
