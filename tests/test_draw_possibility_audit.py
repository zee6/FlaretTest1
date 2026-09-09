from __future__ import annotations

import pytest

from football1.draw_possibility_audit import _closeness_auc, _fixed_bins, _linear_draw_rate_slope, _summary


def test_summary_reports_draw_rate_market_gap_and_flat_roi() -> None:
    rows = [
        {"is_draw": True, "p_draw": 0.30, "draw_odds": 3.50},
        {"is_draw": False, "p_draw": 0.28, "draw_odds": 3.60},
    ]
    result = _summary(rows)
    assert result["matches"] == 2
    assert result["draw_rate"] == pytest.approx(0.5)
    assert result["mean_market_draw_probability"] == pytest.approx(0.29)
    assert result["draw_rate_minus_market"] == pytest.approx(0.21)
    assert result["flat_draw_pnl_units"] == pytest.approx(1.5)
    assert result["flat_draw_roi"] == pytest.approx(0.75)


def test_closeness_auc_rewards_draws_with_smaller_home_away_gap() -> None:
    rows = [
        {"is_draw": True, "home_away_gap": 0.01},
        {"is_draw": True, "home_away_gap": 0.03},
        {"is_draw": False, "home_away_gap": 0.12},
        {"is_draw": False, "home_away_gap": 0.20},
    ]
    assert _closeness_auc(rows) == pytest.approx(1.0)


def test_fixed_bins_are_disjoint() -> None:
    rows = [
        {"home_away_gap": 0.01, "is_draw": True, "p_draw": 0.30, "draw_odds": 3.4},
        {"home_away_gap": 0.03, "is_draw": False, "p_draw": 0.29, "draw_odds": 3.5},
        {"home_away_gap": 0.07, "is_draw": False, "p_draw": 0.27, "draw_odds": 3.7},
    ]
    bins = (("a", 0.0, 0.02), ("b", 0.02, 0.05), ("c", 0.05, 0.10))
    result = _fixed_bins(rows, bins, "home_away_gap")
    assert [r["matches"] for r in result] == [1, 1, 1]


def test_linear_draw_rate_slope_detects_rising_sequence() -> None:
    seasons = [
        {"season_start_year": 2022, "draw_rate": 0.20},
        {"season_start_year": 2023, "draw_rate": 0.22},
        {"season_start_year": 2024, "draw_rate": 0.24},
    ]
    assert _linear_draw_rate_slope(seasons) == pytest.approx(0.02)
