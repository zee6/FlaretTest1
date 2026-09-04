from __future__ import annotations

import pytest

from football1.historical_closing_line import closing_odds_from_raw, movement_record


def test_closing_odds_parser_requires_complete_valid_b365_triplet() -> None:
    assert closing_odds_from_raw({"B365CH": "2.10", "B365CD": "3.40", "B365CA": "3.80"}) == (
        2.10,
        3.40,
        3.80,
    )
    assert closing_odds_from_raw({"B365CH": "2.10", "B365CD": "", "B365CA": "3.80"}) is None
    assert closing_odds_from_raw({"B365CH": "1.00", "B365CD": "3.40", "B365CA": "3.80"}) is None


def test_movement_toward_model_is_positive_without_changing_prediction() -> None:
    opening = (0.50, 0.30, 0.20)
    model = (0.55, 0.28, 0.17)
    closing = (0.53, 0.29, 0.18)
    row = movement_record(opening, closing, model)

    assert row["opening_l1_distance_to_model"] == pytest.approx(0.10)
    assert row["closing_l1_distance_to_model"] == pytest.approx(0.04)
    assert row["l1_distance_reduction"] == pytest.approx(0.06)
    assert row["closing_market_is_closer_to_model"] is True
    assert row["market_movement_aligns_with_model"] is True
    assert row["model_call"] == "home"
    assert row["model_call_market_move"] == pytest.approx(0.03)
    assert row["model_call_moved_toward"] is True


def test_movement_away_from_model_is_negative() -> None:
    opening = (0.50, 0.30, 0.20)
    model = (0.55, 0.28, 0.17)
    closing = (0.47, 0.31, 0.22)
    row = movement_record(opening, closing, model)

    assert float(row["l1_distance_reduction"]) < 0
    assert row["closing_market_is_closer_to_model"] is False
    assert float(row["directional_dot_product"]) < 0
    assert row["market_movement_aligns_with_model"] is False
    assert row["model_call_moved_toward"] is False
