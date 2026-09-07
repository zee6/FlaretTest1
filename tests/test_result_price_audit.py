from __future__ import annotations

import pytest

from football1.result_price_audit import summarize_result_price_records


def _record(
    *,
    match_id: str,
    result_index: int,
    model: tuple[float, float, float],
    market: tuple[float, float, float],
    odds: tuple[float, float, float],
    season: int = 2020,
) -> dict:
    evs = tuple(model[i] * odds[i] - 1.0 for i in range(3))
    call = max(range(3), key=lambda i: model[i])
    best = max(range(3), key=lambda i: evs[i])
    return {
        "match_id": match_id,
        "season_start_year": season,
        "match_date": f"{season}-09-01",
        "result": ("H", "D", "A")[result_index],
        "result_index": result_index,
        "market_probability": market,
        "model_probability": model,
        "odds": odds,
        "ev": evs,
        "result_call_index": call,
        "result_call": ("H", "D", "A")[call],
        "result_call_ev": evs[call],
        "result_call_positive_ev": evs[call] > 0.0,
        "best_ev_index": best,
        "best_ev_outcome": ("H", "D", "A")[best],
        "best_ev": evs[best],
        "best_ev_positive": evs[best] > 0.0,
    }


def test_result_plus_price_is_distinct_from_alternative_price_interest() -> None:
    gold = _record(
        match_id="gold",
        result_index=0,
        model=(0.55, 0.25, 0.20),
        market=(0.50, 0.28, 0.22),
        odds=(1.90, 3.50, 4.70),
    )
    alternative = _record(
        match_id="alt",
        result_index=0,
        model=(0.45, 0.30, 0.25),
        market=(0.47, 0.28, 0.25),
        odds=(2.05, 3.80, 4.10),
    )
    report = summarize_result_price_records([gold, alternative])

    assert report["matches"] == 2
    assert report["classes"]["result_plus_price_raw_interest"]["matches"] == 1
    assert report["classes"]["result_plus_price_and_best_price"]["matches"] == 1
    assert report["classes"]["alternative_price_raw_interest"]["matches"] == 1
    assert report["classes"]["any_positive_price_raw_interest"]["matches"] == 2


def test_raw_interest_uses_mathematical_break_even_only() -> None:
    record = _record(
        match_id="tiny",
        result_index=0,
        model=(0.5001, 0.2799, 0.22),
        market=(0.49, 0.29, 0.22),
        odds=(2.0, 3.4, 4.6),
    )
    report = summarize_result_price_records([record])
    block = report["classes"]["result_plus_price_raw_interest"]

    assert block["matches"] == 1
    assert block["mean_raw_model_ev"] == pytest.approx(0.0002)
    # Presence in this descriptive class must not imply any validated materiality cutoff.
    assert "threshold" not in block


def test_bet_summary_preserves_model_market_and_quote_anatomy() -> None:
    record = _record(
        match_id="anatomy",
        result_index=0,
        model=(0.55, 0.25, 0.20),
        market=(0.50, 0.28, 0.22),
        odds=(1.90, 3.50, 4.70),
    )
    block = summarize_result_price_records([record])["classes"]["result_plus_price_raw_interest"]
    break_even = 1.0 / 1.90

    assert block["mean_model_edge_vs_market"] == pytest.approx(0.05)
    assert block["mean_market_minus_break_even"] == pytest.approx(0.50 - break_even)
    assert block["mean_total_probability_edge_vs_quote"] == pytest.approx(0.55 - break_even)
    assert block["mean_raw_model_ev"] == pytest.approx(0.045)


def test_no_positive_price_class_is_counted_without_bet_metrics() -> None:
    record = _record(
        match_id="pass",
        result_index=0,
        model=(0.52, 0.27, 0.21),
        market=(0.51, 0.28, 0.21),
        odds=(1.80, 3.40, 4.40),
    )
    report = summarize_result_price_records([record])

    assert report["classes"]["any_positive_price_raw_interest"]["matches"] == 0
    assert report["classes"]["no_positive_price"]["matches"] == 1


def test_result_call_accuracy_is_reported_for_all_records() -> None:
    records = [
        _record(
            match_id="1",
            result_index=0,
            model=(0.60, 0.22, 0.18),
            market=(0.58, 0.23, 0.19),
            odds=(1.60, 4.0, 5.0),
        ),
        _record(
            match_id="2",
            result_index=2,
            model=(0.55, 0.25, 0.20),
            market=(0.54, 0.25, 0.21),
            odds=(1.70, 3.8, 4.6),
        ),
    ]
    report = summarize_result_price_records(records)
    assert report["result_call_accuracy"] == pytest.approx(0.5)
