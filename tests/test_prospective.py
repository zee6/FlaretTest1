import json
from pathlib import Path

import pytest

from football1.features import FeatureRow
from football1.prospective import (
    append_prediction_records,
    canonical_team_name,
    make_prediction_record,
    prediction_content_hash,
)


def _feature_row() -> FeatureRow:
    return FeatureRow(
        match_id="event-1",
        season_start_year=2026,
        match_date="2026-09-05",
        home_team="Man United",
        away_team="Man City",
        result="",
        elo_diff=10.0,
        ppg5_diff=0.1,
        gf5_diff=0.2,
        ga5_diff=-0.1,
        shots5_diff=1.0,
        shots_allowed5_diff=-1.0,
        sot5_diff=0.5,
        sot_allowed5_diff=-0.5,
        ppg10_diff=0.05,
        gf10_diff=0.1,
        ga10_diff=-0.05,
        rest_days_diff=1.0,
        log_prior_games_home=5.0,
        log_prior_games_away=5.0,
        b365_home=None,
        b365_draw=None,
        b365_away=None,
    )


def _event() -> dict:
    return {
        "event_id": "event-1",
        "commence_time": "2026-09-05T14:00:00Z",
        "home_team": "Manchester United",
        "away_team": "Manchester City",
        "complete_h2h_bookmaker_count": 20,
        "consensus_fair_probability": {"home": 0.30, "draw": 0.25, "away": 0.45},
        "best_decimal_odds": {"home": 3.5, "draw": 4.1, "away": 2.3},
    }


def test_team_aliases_are_explicit():
    assert canonical_team_name("Manchester United") == "Man United"
    assert canonical_team_name("Brighton and Hove Albion") == "Brighton"
    assert canonical_team_name("Arsenal") == "Arsenal"


def test_prediction_record_is_pre_kickoff_hashed_and_has_no_strategy_threshold():
    record = make_prediction_record(
        event=_event(),
        snapshot_retrieved_at_utc="2026-09-04T09:00:00+00:00",
        model_probability=(0.31, 0.24, 0.45),
        feature_row=_feature_row(),
        training_matches=5000,
        historical_data_cutoff="2026-08-31",
    )
    assert record["status"] == "prediction_locked"
    assert record["model"]["strategy_threshold"] is None
    assert record["model"]["anchor_change_status"] == "prospective_experimental_not_historically_equivalent"
    assert record["model"]["predicted_ev_at_best_odds"]["home"] == pytest.approx(0.085)
    unsigned = dict(record)
    stored = unsigned.pop("content_sha256")
    assert stored == prediction_content_hash(unsigned)


def test_prediction_after_kickoff_is_rejected():
    with pytest.raises(ValueError, match="before kickoff"):
        make_prediction_record(
            event=_event(),
            snapshot_retrieved_at_utc="2026-09-05T15:00:00+00:00",
            model_probability=(0.31, 0.24, 0.45),
            feature_row=_feature_row(),
            training_matches=5000,
            historical_data_cutoff="2026-08-31",
        )


def test_append_is_idempotent_and_verifies_existing_hash(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    record = make_prediction_record(
        event=_event(),
        snapshot_retrieved_at_utc="2026-09-04T09:00:00+00:00",
        model_probability=(0.31, 0.24, 0.45),
        feature_row=_feature_row(),
        training_matches=5000,
        historical_data_cutoff="2026-08-31",
    )
    assert append_prediction_records(ledger, [record]) == 1
    original = ledger.read_text(encoding="utf-8")
    assert append_prediction_records(ledger, [record]) == 0
    assert ledger.read_text(encoding="utf-8") == original

    tampered = json.loads(original)
    tampered["model"]["probability"]["home"] = 0.99
    ledger.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash verification"):
        append_prediction_records(ledger, [])


def test_later_market_snapshot_does_not_duplicate_same_model_lock(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    first = make_prediction_record(
        event=_event(),
        snapshot_retrieved_at_utc="2026-09-04T09:00:00+00:00",
        model_probability=(0.31, 0.24, 0.45),
        feature_row=_feature_row(),
        training_matches=5000,
        historical_data_cutoff="2026-08-31",
    )
    later = make_prediction_record(
        event=_event(),
        snapshot_retrieved_at_utc="2026-09-04T10:00:00+00:00",
        model_probability=(0.32, 0.23, 0.45),
        feature_row=_feature_row(),
        training_matches=5000,
        historical_data_cutoff="2026-08-31",
    )
    assert first["record_id"] != later["record_id"]
    assert append_prediction_records(ledger, [first]) == 1
    locked = ledger.read_text(encoding="utf-8")
    assert append_prediction_records(ledger, [later]) == 0
    assert ledger.read_text(encoding="utf-8") == locked
