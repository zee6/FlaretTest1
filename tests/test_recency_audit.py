from __future__ import annotations

import pytest

from football1.features import TeamGame
from football1.recency_audit import recency_weight, weighted_smoothed_mean


def _game(match_date: str, points: float) -> TeamGame:
    return TeamGame(
        match_date=match_date,
        points=points,
        goals_for=0.0,
        goals_against=0.0,
        shots_for=None,
        shots_against=None,
        sot_for=None,
        sot_against=None,
    )


def test_recency_weight_has_expected_half_life() -> None:
    assert recency_weight(0, 30.0) == pytest.approx(1.0)
    assert recency_weight(30, 30.0) == pytest.approx(0.5)
    assert recency_weight(60, 30.0) == pytest.approx(0.25)


def test_more_recent_match_has_more_influence() -> None:
    games = [
        _game("2026-01-01", 0.0),
        _game("2026-01-29", 3.0),
    ]
    value = weighted_smoothed_mean(
        games,
        current_date="2026-01-31",
        attribute="points",
        neutral=0.0,
        half_life_days=14.0,
    )

    # With zero-valued neutral prior and old result, the recent 3-point result
    # must pull the weighted mean above the simple two-match mean after the
    # same prior smoothing is applied.
    simple_with_prior = 3.0 / (2.0 + 2.0)
    assert value > simple_with_prior


def test_reversing_dates_reverses_recency_preference() -> None:
    recent_win = weighted_smoothed_mean(
        [_game("2026-01-01", 0.0), _game("2026-01-29", 3.0)],
        current_date="2026-01-31",
        attribute="points",
        neutral=1.35,
        half_life_days=14.0,
    )
    recent_loss = weighted_smoothed_mean(
        [_game("2026-01-01", 3.0), _game("2026-01-29", 0.0)],
        current_date="2026-01-31",
        attribute="points",
        neutral=1.35,
        half_life_days=14.0,
    )

    assert recent_win > recent_loss


def test_missing_values_do_not_receive_weight() -> None:
    game = TeamGame(
        match_date="2026-01-29",
        points=3.0,
        goals_for=2.0,
        goals_against=0.0,
        shots_for=None,
        shots_against=None,
        sot_for=None,
        sot_against=None,
    )
    value = weighted_smoothed_mean(
        [game],
        current_date="2026-01-31",
        attribute="shots_for",
        neutral=12.0,
        half_life_days=30.0,
    )
    assert value == pytest.approx(12.0)


def test_invalid_recency_arguments_are_rejected() -> None:
    with pytest.raises(ValueError):
        recency_weight(1, 0.0)
    with pytest.raises(ValueError):
        recency_weight(-1, 30.0)
