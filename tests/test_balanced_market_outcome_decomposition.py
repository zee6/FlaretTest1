from __future__ import annotations

import pytest

from football1.balanced_market_outcome_decomposition import _summary


def test_summary_decomposes_actual_market_residual_and_roi() -> None:
    rows = [
        {
            "result": "draw",
            "probability": {"home": 0.36, "draw": 0.28, "away": 0.36},
            "odds": {"home": 2.8, "draw": 3.5, "away": 2.8},
        },
        {
            "result": "home",
            "probability": {"home": 0.38, "draw": 0.29, "away": 0.33},
            "odds": {"home": 2.6, "draw": 3.4, "away": 3.0},
        },
    ]
    result = _summary(rows)
    assert result["matches"] == 2
    assert result["outcomes"]["draw"]["actual_frequency"] == pytest.approx(0.5)
    assert result["outcomes"]["draw"]["mean_market_probability"] == pytest.approx(0.285)
    assert result["outcomes"]["draw"]["actual_minus_market"] == pytest.approx(0.215)
    assert result["outcomes"]["draw"]["flat_pnl_units"] == pytest.approx(1.5)
    assert result["outcomes"]["draw"]["flat_roi"] == pytest.approx(0.75)


def test_outcome_frequencies_sum_to_one() -> None:
    rows = [
        {
            "result": "home",
            "probability": {"home": 0.4, "draw": 0.3, "away": 0.3},
            "odds": {"home": 2.5, "draw": 3.3, "away": 3.3},
        },
        {
            "result": "draw",
            "probability": {"home": 0.4, "draw": 0.3, "away": 0.3},
            "odds": {"home": 2.5, "draw": 3.3, "away": 3.3},
        },
        {
            "result": "away",
            "probability": {"home": 0.4, "draw": 0.3, "away": 0.3},
            "odds": {"home": 2.5, "draw": 3.3, "away": 3.3},
        },
    ]
    result = _summary(rows)
    total = sum(result["outcomes"][outcome]["actual_frequency"] for outcome in ("home", "draw", "away"))
    residual_total = sum(result["outcomes"][outcome]["actual_minus_market"] for outcome in ("home", "draw", "away"))
    assert total == pytest.approx(1.0)
    assert residual_total == pytest.approx(0.0)


def test_empty_summary_is_explicit() -> None:
    result = _summary([])
    assert result["matches"] == 0
    assert result["outcomes"]["home"]["actual_frequency"] is None
    assert result["outcomes"]["draw"]["flat_roi"] is None
