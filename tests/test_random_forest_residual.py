from __future__ import annotations

import math

import pytest

from football1.features import FeatureRow
from football1.random_forest_residual import (
    RF_FEATURE_NAMES,
    _economic_metrics,
    geometric_market_correction,
    random_forest_vector,
)


def _row() -> FeatureRow:
    return FeatureRow(
        match_id="m1",
        season_start_year=2025,
        match_date="2025-08-16",
        home_team="Home",
        away_team="Away",
        result="H",
        elo_diff=25.0,
        ppg5_diff=0.2,
        gf5_diff=0.1,
        ga5_diff=-0.1,
        shots5_diff=1.0,
        shots_allowed5_diff=-0.5,
        sot5_diff=0.4,
        sot_allowed5_diff=-0.2,
        ppg10_diff=0.15,
        gf10_diff=0.08,
        ga10_diff=-0.05,
        rest_days_diff=1.0,
        log_prior_games_home=4.0,
        log_prior_games_away=4.1,
        b365_home=2.0,
        b365_draw=3.6,
        b365_away=4.2,
    )


def test_geometric_market_correction_endpoints() -> None:
    market = (0.50, 0.28, 0.22)
    candidate = (0.60, 0.25, 0.15)
    assert geometric_market_correction(market, candidate, weight=0.0) == pytest.approx(market)
    assert geometric_market_correction(market, candidate, weight=1.0) == pytest.approx(candidate)


def test_geometric_market_correction_is_probability_triplet() -> None:
    mixed = geometric_market_correction((0.50, 0.28, 0.22), (0.60, 0.25, 0.15), weight=0.10)
    assert all(0.0 < p < 1.0 for p in mixed)
    assert sum(mixed) == pytest.approx(1.0)
    assert 0.50 < mixed[0] < 0.60


def test_random_forest_vector_includes_market_starting_point() -> None:
    row = _row()
    vector = random_forest_vector(row)
    assert len(vector) == len(RF_FEATURE_NAMES)
    market_tail = vector[-3:]
    assert sum(market_tail) == pytest.approx(1.0)
    assert all(math.isfinite(x) for x in vector)


def test_economic_metrics_uses_single_best_positive_ev_outcome() -> None:
    row = _row()
    metrics = _economic_metrics([((0.55, 0.25, 0.20), row)])
    positive = metrics["positive_model_ev_no_threshold"]
    assert positive["bets"] == 1
    assert positive["wins"] == 1
    assert positive["pnl_units"] == pytest.approx(1.0)
    assert positive["roi"] == pytest.approx(1.0)
