from __future__ import annotations

import math

import pytest

from football1.opportunity_layer import (
    analyze_locked_prediction,
    non_loss_analysis,
    price_opportunity_analysis,
    synthetic_dutch_odds,
)


def test_price_layer_separates_result_call_from_best_price() -> None:
    result = price_opportunity_analysis(
        model_probability={"home": 0.38, "draw": 0.31, "away": 0.31},
        market_probability={"home": 0.42, "draw": 0.27, "away": 0.31},
        best_decimal_odds={"home": 2.20, "draw": 3.80, "away": 3.60},
    )

    assert result["result_call"] == "home"
    assert result["best_price_outcome"] == "draw"
    assert result["result_plus_price_raw_interest"] is False
    assert result["outcomes"]["draw"]["model_ev_at_quoted_odds"] == pytest.approx(0.178)
    assert result["decision_weight"] == 0.0
    assert result["betting_threshold"] is None


def test_edge_anatomy_separates_model_disagreement_from_quote_premium() -> None:
    result = price_opportunity_analysis(
        model_probability={"home": 0.38, "draw": 0.31, "away": 0.31},
        market_probability={"home": 0.42, "draw": 0.27, "away": 0.31},
        best_decimal_odds={"home": 2.20, "draw": 3.80, "away": 3.60},
    )
    anatomy = result["outcomes"]["draw"]["edge_anatomy"]
    break_even = 1.0 / 3.80

    assert anatomy["model_probability_edge_vs_market"] == pytest.approx(0.04)
    assert anatomy["quote_probability_edge_vs_market"] == pytest.approx(0.27 - break_even)
    assert anatomy["total_probability_edge_vs_quote"] == pytest.approx(0.31 - break_even)
    assert anatomy["total_probability_edge_vs_quote"] == pytest.approx(
        anatomy["model_probability_edge_vs_market"]
        + anatomy["quote_probability_edge_vs_market"]
    )
    assert anatomy["model_ev_at_quoted_odds"] == pytest.approx(0.178)
    assert result["best_model_disagreement_outcome"] == "draw"


def test_long_odds_ev_can_be_large_with_small_model_edge() -> None:
    result = price_opportunity_analysis(
        model_probability={"home": 0.8063, "draw": 0.1242, "away": 0.0695},
        market_probability={"home": 0.8142, "draw": 0.1200, "away": 0.0658},
        best_decimal_odds={"home": 1.19, "draw": 9.0, "away": 18.0},
    )
    away = result["outcomes"]["away"]
    anatomy = away["edge_anatomy"]

    assert away["model_ev_at_quoted_odds"] == pytest.approx(0.251, abs=1e-3)
    assert anatomy["model_probability_edge_vs_market"] == pytest.approx(0.0037)
    assert anatomy["quote_probability_edge_vs_market"] > anatomy["model_probability_edge_vs_market"]
    assert anatomy["total_probability_edge_vs_quote"] == pytest.approx(
        anatomy["model_probability_edge_vs_market"]
        + anatomy["quote_probability_edge_vs_market"]
    )


def test_result_plus_price_flag_is_raw_interest_only() -> None:
    result = price_opportunity_analysis(
        model_probability={"home": 0.52, "draw": 0.27, "away": 0.21},
        market_probability={"home": 0.49, "draw": 0.28, "away": 0.23},
        best_decimal_odds={"home": 2.05, "draw": 3.70, "away": 4.80},
    )

    assert result["result_call"] == "home"
    assert result["result_plus_price_raw_interest"] is True
    assert result["result_plus_price_model_ev"] == pytest.approx(0.066)
    assert result["stake_rule"] is None


def test_synthetic_dutch_odds_equalizes_two_leg_cover() -> None:
    combined = synthetic_dutch_odds(3.80, 3.60)
    expected = 1.0 / ((1.0 / 3.80) + (1.0 / 3.60))
    assert combined == pytest.approx(expected)


def test_non_loss_analyzes_outsider_plus_draw_as_one_event() -> None:
    result = non_loss_analysis(
        model_probability={"home": 0.38, "draw": 0.31, "away": 0.31},
        market_probability={"home": 0.42, "draw": 0.27, "away": 0.31},
        best_decimal_odds={"home": 2.20, "draw": 3.80, "away": 3.60},
    )

    x2 = result["away_or_draw"]
    assert result["market_outsider_side"] == "away"
    assert result["outsider_non_loss"]["id"] == "X2"
    assert x2["model_probability"] == pytest.approx(0.62)
    assert x2["market_probability"] == pytest.approx(0.58)
    assert x2["model_ev_at_synthetic_odds"] > 0.0
    anatomy = x2["edge_anatomy"]
    assert anatomy["model_probability_edge_vs_market"] == pytest.approx(0.04)
    assert anatomy["total_probability_edge_vs_quote"] == pytest.approx(
        anatomy["model_probability_edge_vs_market"]
        + anatomy["quote_probability_edge_vs_market"]
    )
    assert result["decision_weight"] == 0.0


def test_locked_prediction_analysis_preserves_interface_deferred_contract() -> None:
    record = {
        "record_id": "abc",
        "event_id": "evt",
        "status": "prediction_locked",
        "market_anchor": {
            "probability": {"home": 0.42, "draw": 0.27, "away": 0.31},
            "best_decimal_odds": {"home": 2.20, "draw": 3.80, "away": 3.60},
        },
        "model": {"probability": {"home": 0.38, "draw": 0.31, "away": 0.31}},
        "features": {"elo_diff": -12.5},
    }

    result = analyze_locked_prediction(record)
    assert result["schema_version"] == 2
    assert result["source_record_id"] == "abc"
    assert result["price"]["best_price_outcome"] == "draw"
    assert result["non_loss"]["outsider_non_loss"]["id"] == "X2"
    assert result["draw_shape_inputs"]["absolute_elo_difference"] == pytest.approx(12.5)
    assert result["interface_status"] == "data_contract_ready_interface_deferred"


def test_invalid_probability_vector_is_rejected() -> None:
    with pytest.raises(ValueError):
        price_opportunity_analysis(
            model_probability={"home": 0.40, "draw": 0.30, "away": 0.20},
            market_probability={"home": 0.42, "draw": 0.27, "away": 0.31},
            best_decimal_odds={"home": 2.20, "draw": 3.80, "away": 3.60},
        )

    with pytest.raises(ValueError):
        synthetic_dutch_odds(math.inf, 3.0)
