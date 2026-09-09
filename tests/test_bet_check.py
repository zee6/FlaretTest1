import pytest

from football1.bet_check import classify_price, evaluate_bet, evaluate_leg


def _reference(
    event_id: str,
    *,
    market=(0.50, 0.25, 0.25),
    model=(0.52, 0.24, 0.24),
    best=(2.10, 4.10, 4.20),
):
    return {
        "event_id": event_id,
        "home_team": f"{event_id} Home",
        "away_team": f"{event_id} Away",
        "market_probability": dict(zip(("home", "draw", "away"), market)),
        "football1_probability": dict(zip(("home", "draw", "away"), model)),
        "best_observed_price": {
            "home": {
                "odds": best[0],
                "bookmaker_key": "book_a",
                "bookmaker_title": "Book A",
                "observed_at_utc": "2026-09-09T09:00:00Z",
                "books_checked": 15,
            },
            "draw": {"odds": best[1], "bookmaker_key": "book_b", "bookmaker_title": "Book B"},
            "away": {"odds": best[2], "bookmaker_key": "book_c", "bookmaker_title": "Book C"},
        },
    }


def _leg(event_id: str, outcome: str, odds: float):
    return {
        "event_id": event_id,
        "market": "h2h",
        "outcome": outcome,
        "quoted_odds": odds,
    }


def test_price_quality_distinguishes_exact_near_and_materially_worse() -> None:
    assert classify_price(2.10, 2.10)["status"] == "best_observed"
    assert classify_price(2.09, 2.10)["status"] == "near_best_within_1pct"
    assert classify_price(2.07, 2.10)["status"] == "near_best_within_2pct"
    assert classify_price(2.00, 2.10)["status"] == "materially_below_best"
    assert classify_price(2.20, 2.10)["status"] == "better_than_observed_best"
    assert classify_price(2.00, None)["status"] == "best_price_unknown"


def test_single_leg_calculations_are_deterministic() -> None:
    reference = _reference("e1")
    result = evaluate_bet(
        {"currency": "GBP", "stake": 10.0, "legs": [_leg("e1", "home", 2.0)]},
        [reference],
    )
    assert result["engine"] == "deterministic_local_bet_check_v1"
    assert result["bet_type"] == "single"
    assert result["legs"][0]["user_quote"]["break_even_probability"] == pytest.approx(0.5)
    assert result["legs"][0]["market"]["probability"] == pytest.approx(0.50)
    assert result["legs"][0]["football1"]["probability"] == pytest.approx(0.52)
    assert result["legs"][0]["football1"]["fair_odds"] == pytest.approx(1 / 0.52)
    assert result["combined"]["potential_gross_return"] == pytest.approx(20.0)
    assert result["governance"]["uses_llm"] is False
    assert result["input_contract"]["network_required_by_core"] is False


def test_best_price_never_changes_probability() -> None:
    ref_a = _reference("e1", best=(2.0, 4.0, 4.0))
    ref_b = _reference("e1", best=(3.0, 5.0, 5.0))
    leg = _leg("e1", "home", 2.0)
    a = evaluate_leg(leg, ref_a)
    b = evaluate_leg(leg, ref_b)
    assert a["market"]["probability"] == pytest.approx(b["market"]["probability"])
    assert a["football1"]["probability"] == pytest.approx(b["football1"]["probability"])
    assert a["price_quality"]["status"] != b["price_quality"]["status"]


def test_distinct_event_accumulator_has_independence_only_combined_view() -> None:
    result = evaluate_bet(
        {
            "currency": "GBP",
            "stake": 5.0,
            "legs": [_leg("e1", "home", 2.0), _leg("e2", "away", 4.0)],
        },
        [_reference("e1"), _reference("e2")],
    )
    assert result["bet_type"] == "accumulator"
    assert result["combined"]["joint_probability_status"] == "independence_only_distinct_events"
    assert result["combined"]["market_independence_probability"] == pytest.approx(0.50 * 0.25)
    assert result["combined"]["football1_independence_probability"] == pytest.approx(0.52 * 0.24)
    assert result["combined"]["user_combined_odds"] == pytest.approx(8.0)


def test_same_event_multi_leg_refuses_fake_joint_probability() -> None:
    result = evaluate_bet(
        {
            "currency": "GBP",
            "stake": 5.0,
            "legs": [_leg("e1", "home", 2.0), _leg("e1", "draw", 4.0)],
        },
        [_reference("e1")],
    )
    assert result["combined"]["joint_probability_status"] == "unsupported_correlated_same_event"
    assert result["combined"]["market_independence_probability"] is None
    assert result["combined"]["football1_independence_probability"] is None


def test_supplied_combined_price_is_compared_with_leg_product() -> None:
    result = evaluate_bet(
        {
            "currency": "GBP",
            "stake": 10.0,
            "quoted_combined_odds": 7.5,
            "legs": [_leg("e1", "home", 2.0), _leg("e2", "away", 4.0)],
        },
        [_reference("e1"), _reference("e2")],
    )
    assert result["combined"]["combined_odds_source"] == "user_supplied"
    assert result["combined"]["product_of_user_leg_odds"] == pytest.approx(8.0)
    assert result["combined"]["combined_odds_vs_leg_product"] == pytest.approx(7.5 / 8.0 - 1.0)
    assert result["combined"]["potential_gross_return"] == pytest.approx(75.0)


def test_weakest_leg_uses_conservative_market_arithmetic_not_largest_model_residual() -> None:
    # e1 has a large positive Football 1 residual but a good user price.
    r1 = _reference("e1", market=(0.40, 0.30, 0.30), model=(0.48, 0.27, 0.25), best=(2.6, 3.5, 3.5))
    # e2 has almost no Football 1 disagreement but a distinctly poor user price.
    r2 = _reference("e2", market=(0.50, 0.25, 0.25), model=(0.51, 0.245, 0.245), best=(2.2, 4.2, 4.2))
    result = evaluate_bet(
        {
            "currency": "GBP",
            "stake": 10.0,
            "legs": [_leg("e1", "home", 2.6), _leg("e2", "home", 1.8)],
        },
        [r1, r2],
    )
    assert result["weakest_leg"]["event_id"] == "e2"
    assert "de-vigged market arithmetic EV" in result["weakest_leg"]["basis"]


def test_unsupported_markets_and_currency_are_rejected() -> None:
    reference = _reference("e1")
    with pytest.raises(ValueError, match="Unsupported market"):
        evaluate_bet(
            {"currency": "GBP", "stake": 10.0, "legs": [{**_leg("e1", "home", 2.0), "market": "both_teams_to_score"}]},
            [reference],
        )
    with pytest.raises(ValueError, match="currency is GBP"):
        evaluate_bet(
            {"currency": "CHF", "stake": 10.0, "legs": [_leg("e1", "home", 2.0)]},
            [reference],
        )
