from __future__ import annotations

from datetime import date

import pytest

from football1.congestion_residual import (
    CONGESTION_FEATURE_NAMES,
    CongestionRow,
    _recent_count,
    _rest_days,
    congestion_vector,
    fit_congestion_residual,
)
from football1.features import FeatureRow


def _base(match_id: str, result: str, home_odds: float = 2.2, draw_odds: float = 3.4, away_odds: float = 3.4) -> FeatureRow:
    return FeatureRow(
        match_id=match_id,
        season_start_year=2025,
        match_date="2025-09-01",
        home_team="Home",
        away_team="Away",
        result=result,
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
        log_prior_games_home=3.0,
        log_prior_games_away=3.0,
        b365_home=home_odds,
        b365_draw=draw_odds,
        b365_away=away_odds,
    )


def _row(match_id: str, result: str, offset: float) -> CongestionRow:
    return CongestionRow(
        base=_base(match_id, result),
        home_rest_days=5.0 + offset,
        away_rest_days=6.0,
        home_matches_previous_7_days=1.0,
        away_matches_previous_7_days=1.0,
        home_matches_previous_14_days=2.0 + offset / 10.0,
        away_matches_previous_14_days=2.0,
    )


def test_schedule_windows_exclude_current_day_and_cap_rest() -> None:
    history = [date(2025, 8, 20), date(2025, 8, 27), date(2025, 8, 30)]
    current = date(2025, 9, 1)
    assert _rest_days(history, current) == 2.0
    assert _recent_count(history, current, 7) == 2.0
    assert _recent_count(history, current, 14) == 3.0
    assert _rest_days([], current) == 7.0
    assert _rest_days([date(2025, 6, 1)], current) == 30.0


def test_congestion_vector_has_frozen_feature_order() -> None:
    row = _row("m1", "H", 0.0)
    vector = congestion_vector(row)
    assert len(vector) == len(CONGESTION_FEATURE_NAMES)
    assert vector == [5.0, 6.0, 1.0, 1.0, 2.0, 2.0]


def test_fitted_residual_returns_probability_triplet() -> None:
    rows = [
        _row("h1", "H", 1.0),
        _row("h2", "H", 2.0),
        _row("d1", "D", 0.0),
        _row("d2", "D", 0.2),
        _row("a1", "A", -1.0),
        _row("a2", "A", -2.0),
    ]
    model = fit_congestion_residual(rows, alpha=0.10)
    probs = model.predict(_row("test", "H", 0.5))
    assert len(probs) == 3
    assert all(0.0 < value < 1.0 for value in probs)
    assert sum(probs) == pytest.approx(1.0)


def test_alpha_must_be_positive() -> None:
    with pytest.raises(ValueError):
        fit_congestion_residual([_row("h", "H", 1.0), _row("d", "D", 0.0), _row("a", "A", -1.0)], alpha=0.0)
