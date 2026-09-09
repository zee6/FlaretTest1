import json
from pathlib import Path

import pytest

from football1.price_shopping_audit import (
    build_quote_observations,
    greedy_best_price_coverage,
    locked_snapshot_join_diagnostic,
    price_shopping_audit,
    quote_observation,
)


def _record(record_id="r1", event_id="e1", retrieved="2026-09-04T09:00:00+00:00"):
    return {
        "record_id": record_id,
        "status": "pre_kickoff_odds_snapshot",
        "event_id": event_id,
        "retrieved_at_utc": retrieved,
        "commence_time_utc": "2026-09-05T15:00:00Z",
        "home_team": "Home",
        "away_team": "Away",
        "consensus_fair_probability": {"home": 0.5, "draw": 0.25, "away": 0.25},
        "bookmakers": [
            {
                "bookmaker_key": "book_a",
                "bookmaker_title": "Book A",
                "last_update_utc": "2026-09-04T08:59:00Z",
                "decimal_odds": {"home": 2.0, "draw": 3.6, "away": 4.0},
            },
            {
                "bookmaker_key": "book_b",
                "bookmaker_title": "Book B",
                "last_update_utc": "2026-09-04T08:59:30Z",
                "decimal_odds": {"home": 2.2, "draw": 3.8, "away": 3.8},
            },
            {
                "bookmaker_key": "book_c",
                "bookmaker_title": "Book C",
                "last_update_utc": "2026-09-04T08:59:45Z",
                "decimal_odds": {"home": 2.1, "draw": 3.7, "away": 4.1},
            },
            {
                "bookmaker_key": "smarkets",
                "bookmaker_title": "Smarkets",
                "last_update_utc": "2026-09-04T08:59:50Z",
                "decimal_odds": {"home": 2.3, "draw": 3.9, "away": 4.2},
            },
        ],
    }


def test_quote_observation_excludes_raw_exchange_from_default_best() -> None:
    observation = quote_observation(_record(), "home")
    assert observation is not None
    assert observation["best_sportsbook_price"] == pytest.approx(2.2)
    assert observation["median_sportsbook_price"] == pytest.approx(2.1)
    assert observation["best_sportsbook_books"][0]["bookmaker_key"] == "book_b"
    assert observation["best_raw_exchange_price"] == pytest.approx(2.3)
    assert observation["raw_exchange_beats_sportsbook"] is True


def test_best_price_improves_break_even_and_consensus_ev_without_changing_probability() -> None:
    observation = quote_observation(_record(), "home")
    assert observation is not None
    assert observation["consensus_probability"] == pytest.approx(0.5)
    assert observation["gross_return_uplift_best_vs_median"] == pytest.approx(2.2 / 2.1 - 1.0)
    assert observation["break_even_probability_reduction_best_vs_median"] == pytest.approx(1 / 2.1 - 1 / 2.2)
    assert observation["consensus_ev_at_median_sportsbook"] == pytest.approx(0.05)
    assert observation["consensus_ev_at_best_sportsbook"] == pytest.approx(0.10)
    assert observation["consensus_ev_improvement_from_shopping"] == pytest.approx(0.05)


def test_greedy_coverage_counts_tied_best_as_available_at_either_book() -> None:
    first = _record(record_id="r1", event_id="e1")
    second = _record(record_id="r2", event_id="e2", retrieved="2026-09-04T10:00:00+00:00")
    # Make Book A tie Book B on the home outcome in the second observation.
    second["bookmakers"][0]["decimal_odds"]["home"] = 2.2
    observations = build_quote_observations([first, second])
    coverage = greedy_best_price_coverage(observations)
    assert coverage["observations"] == 6
    assert coverage["books_needed_for_50pct"] is not None
    assert coverage["greedy_order"]


def test_locked_snapshot_join_requires_exact_event_and_timestamp() -> None:
    archive = [_record()]
    ledger = [
        {
            "status": "prediction_locked",
            "event_id": "e1",
            "snapshot_retrieved_at_utc": "2026-09-04T09:00:00+00:00",
        },
        {
            "status": "prediction_locked",
            "event_id": "e2",
            "snapshot_retrieved_at_utc": "2026-09-04T09:00:00+00:00",
        },
    ]
    diagnostic = locked_snapshot_join_diagnostic(archive, ledger)
    assert diagnostic["prediction_locks"] == 2
    assert diagnostic["exact_quote_board_matches"] == 1
    assert diagnostic["can_attribute_best_price_effect_to_locked_model_without_timing_mix"] is True


def test_full_audit_is_zero_weight_and_result_independent(tmp_path: Path) -> None:
    archive_path = tmp_path / "odds.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    archive_path.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    ledger_path.write_text(
        json.dumps(
            {
                "status": "prediction_locked",
                "event_id": "e1",
                "snapshot_retrieved_at_utc": "2026-09-04T09:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = price_shopping_audit(archive_path, ledger_path)
    assert report["decision_weight"] == 0.0
    assert report["portfolio_currency"] == "GBP"
    assert report["quote_economics"]["event_snapshots"] == 1
    assert report["quote_economics"]["outcome_quote_observations"] == 3
    assert report["governance"]["settled_result_required_for_price_uplift_measurement"] is False
