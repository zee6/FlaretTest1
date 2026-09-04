from __future__ import annotations

import pytest

from football1.market_consensus_movement import best_price_premium, consensus_odds_from_raw


def test_consensus_odds_parser_requires_complete_first_closing_and_max_triplets() -> None:
    raw = {
        "AvgH": "2.00", "AvgD": "3.40", "AvgA": "4.10",
        "AvgCH": "1.95", "AvgCD": "3.50", "AvgCA": "4.30",
        "MaxH": "2.08", "MaxD": "3.55", "MaxA": "4.35",
    }
    parsed = consensus_odds_from_raw(raw)
    assert parsed is not None
    opening, closing, maximum = parsed
    assert opening == pytest.approx((2.00, 3.40, 4.10))
    assert closing == pytest.approx((1.95, 3.50, 4.30))
    assert maximum == pytest.approx((2.08, 3.55, 4.35))

    incomplete = dict(raw)
    incomplete["AvgCD"] = ""
    assert consensus_odds_from_raw(incomplete) is None


def test_best_price_premium_is_max_over_average_minus_one() -> None:
    premium = best_price_premium((2.00, 3.00, 4.00), (2.10, 3.15, 4.40))
    assert premium == pytest.approx((0.05, 0.05, 0.10))


def test_best_price_premium_rejects_invalid_odds() -> None:
    with pytest.raises(ValueError):
        best_price_premium((1.0, 3.0, 4.0), (1.1, 3.2, 4.2))
