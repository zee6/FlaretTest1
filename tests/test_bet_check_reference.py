from pathlib import Path

import pytest

import football1.bet_check_reference as module
from football1.bet_check import evaluate_bet
from football1.bet_check_reference import reference_from_synchronized_record


SNAPSHOT_TIME = "2026-09-09T09:00:00+00:00"


def _prediction(event_id: str = "e1", timestamp: str = SNAPSHOT_TIME):
    return {
        "status": "prediction_locked",
        "event_id": event_id,
        "commence_time_utc": "2026-09-12T14:00:00Z",
        "snapshot_retrieved_at_utc": timestamp,
        "home_team_provider": "Alpha",
        "away_team_provider": "Beta",
        "market_anchor": {
            "type": "mean_of_individually_devigged_complete_uk_h2h_books",
            "probability": {"home": 0.50, "draw": 0.25, "away": 0.25},
        },
        "model": {
            "id": "model-v1",
            "alpha": 0.10,
            "probability": {"home": 0.52, "draw": 0.24, "away": 0.24},
        },
    }


def _event(event_id: str = "e1"):
    return {
        "event_id": event_id,
        "commence_time": "2026-09-12T14:00:00Z",
        "home_team": "Alpha",
        "away_team": "Beta",
        "quote_board": {
            "home": [
                {"decimal_odds": 2.30, "bookmaker_key": "smarkets", "bookmaker_title": "Smarkets"},
                {"decimal_odds": 2.20, "bookmaker_key": "book_a", "bookmaker_title": "Book A"},
                {"decimal_odds": 2.10, "bookmaker_key": "book_b", "bookmaker_title": "Book B"},
            ],
            "draw": [
                {"decimal_odds": 4.20, "bookmaker_key": "matchbook", "bookmaker_title": "Matchbook"},
                {"decimal_odds": 4.00, "bookmaker_key": "book_a", "bookmaker_title": "Book A"},
            ],
            "away": [
                {"decimal_odds": 4.40, "bookmaker_key": "betfair_ex_uk", "bookmaker_title": "Betfair Exchange"},
                {"decimal_odds": 4.10, "bookmaker_key": "book_b", "bookmaker_title": "Book B"},
            ],
        },
    }


def test_reference_strictly_joins_one_timestamp_and_excludes_raw_exchanges_from_best_price() -> None:
    reference = reference_from_synchronized_record(
        _prediction(),
        _event(),
        snapshot_retrieved_at_utc=SNAPSHOT_TIME,
    )
    assert reference["timing_contract"]["exact_timestamp_match"] is True
    assert reference["best_observed_price"]["home"]["odds"] == pytest.approx(2.20)
    assert reference["best_observed_price"]["home"]["bookmaker_key"] == "book_a"
    assert reference["best_observed_price"]["home"]["books_checked"] == 2
    assert reference["best_observed_price"]["draw"]["odds"] == pytest.approx(4.00)
    assert reference["best_observed_price"]["away"]["odds"] == pytest.approx(4.10)
    assert reference["market_probability"]["home"] == pytest.approx(0.50)
    assert reference["football1_probability"]["home"] == pytest.approx(0.52)


def test_reference_rejects_later_quote_board_for_earlier_model_probability() -> None:
    with pytest.raises(ValueError, match="same snapshot timestamp"):
        reference_from_synchronized_record(
            _prediction(timestamp="2026-09-09T08:00:00+00:00"),
            _event(),
            snapshot_retrieved_at_utc=SNAPSHOT_TIME,
        )


def test_reference_rejects_event_mismatch() -> None:
    with pytest.raises(ValueError, match="event_id do not match"):
        reference_from_synchronized_record(
            _prediction(event_id="e1"),
            _event(event_id="e2"),
            snapshot_retrieved_at_utc=SNAPSHOT_TIME,
        )


def test_builder_reuses_prospective_model_read_only(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_build(db_path, snapshot, *, alpha):
        calls.append((db_path, snapshot, alpha))
        return [_prediction()], {"model_id": "model-v1", "created_records": 1}

    monkeypatch.setattr(module, "build_prospective_records", fake_build)
    snapshot = {
        "retrieved_at_utc": SNAPSHOT_TIME,
        "summary": [_event()],
    }
    references, metadata = module.build_synchronized_bet_check_references(
        tmp_path / "football1.sqlite",
        snapshot,
    )
    assert len(calls) == 1
    assert len(references) == 1
    assert metadata["ledger_written"] is False
    assert metadata["market_anchor_policy_unchanged"] is True
    assert metadata["best_price_universe"] == "sportsbook_only_known_exchanges_excluded"


def test_synchronized_reference_feeds_deterministic_bet_check() -> None:
    reference = reference_from_synchronized_record(
        _prediction(),
        _event(),
        snapshot_retrieved_at_utc=SNAPSHOT_TIME,
    )
    report = evaluate_bet(
        {
            "currency": "GBP",
            "stake": 10.0,
            "legs": [
                {"event_id": "e1", "market": "h2h", "outcome": "home", "quoted_odds": 2.10}
            ],
        },
        [reference],
    )
    assert report["legs"][0]["price_quality"]["status"] == "materially_below_best"
    assert report["legs"][0]["best_price"]["odds"] == pytest.approx(2.20)
    assert report["governance"]["cloud_reasoning_required"] is False
