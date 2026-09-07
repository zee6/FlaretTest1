from __future__ import annotations

from collections import deque

import pytest

from football1.home_away_recency_audit import DatedVenueGame, venue_recency_summary


def test_venue_recency_prefers_newer_result() -> None:
    current = "2026-09-16"
    newer_win = deque([
        DatedVenueGame("2026-08-17", 0.0, 0.0, 2.0),
        DatedVenueGame("2026-09-15", 3.0, 3.0, 0.0),
    ])
    newer_loss = deque([
        DatedVenueGame("2026-08-17", 3.0, 3.0, 0.0),
        DatedVenueGame("2026-09-15", 0.0, 0.0, 2.0),
    ])

    win_ppg, win_gd = venue_recency_summary(newer_win, 10, current_date=current, half_life_days=15.0)
    loss_ppg, loss_gd = venue_recency_summary(newer_loss, 10, current_date=current, half_life_days=15.0)

    assert win_ppg > loss_ppg
    assert win_gd > loss_gd


def test_venue_recency_rejects_future_history() -> None:
    games = deque([DatedVenueGame("2026-09-17", 3.0, 2.0, 0.0)])
    with pytest.raises(ValueError, match="future match"):
        venue_recency_summary(games, 5, current_date="2026-09-16", half_life_days=15.0)


def test_venue_recency_requires_positive_half_life() -> None:
    with pytest.raises(ValueError, match="positive"):
        venue_recency_summary([], 5, current_date="2026-09-16", half_life_days=0.0)
