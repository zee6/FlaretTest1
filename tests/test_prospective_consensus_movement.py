import json

import pytest

from football1.prospective_consensus_movement import (
    append_movement_forecast_records,
    bookmaker_market_shape,
    build_prospective_movement_report,
    common_book_market_pair,
    load_movement_forecast_locks,
    make_movement_forecast_record,
    movement_forecast_content_hash,
)


def quote(key: str, home: float, draw: float, away: float) -> dict:
    return {
        "bookmaker_key": key,
        "bookmaker_title": key.upper(),
        "decimal_odds": {"home": home, "draw": draw, "away": away},
    }


def snapshot(event_id: str, retrieved: str, bookmakers: list[dict]) -> dict:
    return {
        "status": "pre_kickoff_odds_snapshot",
        "event_id": event_id,
        "retrieved_at_utc": retrieved,
        "bookmakers": bookmakers,
    }


def movement_lock() -> dict:
    event = {
        "event_id": "evt-1",
        "commence_time_utc": "2026-09-05T15:00:00Z",
        "home_team": "Home",
        "away_team": "Away",
        "provider": "the-odds-api",
        "sport_key": "soccer_epl",
    }
    shape = bookmaker_market_shape(
        [quote("a", 2.20, 3.40, 3.20), quote("b", 2.24, 3.36, 3.18)]
    )
    return make_movement_forecast_record(
        event=event,
        snapshot_retrieved_at_utc="2026-09-04T12:00:00Z",
        training_matches=1000,
        training_seasons=[2022, 2023, 2024, 2025],
        historical_data_cutoff="2026-09-03",
        live_market_shape=shape,
        training_mean=(0.003, -0.001, -0.002),
        base_move=(0.010, -0.004, -0.006),
        augmented_move=(0.012, -0.005, -0.007),
        features={
            "home_team_canonical": "Home",
            "away_team_canonical": "Away",
            "feature_vector": [0.0],
        },
    )


def test_bookmaker_market_shape_uses_arithmetic_avg_and_max():
    shape = bookmaker_market_shape(
        [quote("a", 2.0, 3.0, 4.0), quote("b", 2.4, 3.4, 3.6)]
    )
    assert shape["bookmaker_count"] == 2
    assert shape["average_decimal_odds"] == pytest.approx(
        {"home": 2.2, "draw": 3.2, "away": 3.8}
    )
    assert shape["maximum_decimal_odds"] == pytest.approx(
        {"home": 2.4, "draw": 3.4, "away": 4.0}
    )
    assert sum(shape["average_odds_devigged_probability"].values()) == pytest.approx(1.0)
    assert shape["best_price_premium"]["home"] == pytest.approx(2.4 / 2.2 - 1.0)


def test_common_book_pair_blocks_bookmaker_composition_drift():
    first = snapshot(
        "evt",
        "2026-09-04T10:00:00Z",
        [quote("a", 2.0, 3.2, 4.0), quote("b", 2.2, 3.1, 3.8)],
    )
    later = snapshot(
        "evt",
        "2026-09-04T11:00:00Z",
        [quote("a", 1.9, 3.3, 4.2), quote("c", 2.8, 2.7, 3.0)],
    )
    pair = common_book_market_pair(first, later, min_common_bookmakers=1)
    assert pair is not None
    assert pair["common_bookmaker_keys"] == ["a"]
    assert pair["common_bookmaker_count"] == 1
    assert pair["initial"]["average_decimal_odds"]["home"] == pytest.approx(2.0)
    assert pair["later"]["average_decimal_odds"]["home"] == pytest.approx(1.9)
    assert common_book_market_pair(first, later, min_common_bookmakers=2) is None


def test_movement_lock_is_hash_verified_and_immutable_per_event(tmp_path):
    row = movement_lock()
    assert row["decision_weight"] == 0.0
    assert sum(row["forecasts"]["base_rf"]["movement"].values()) == pytest.approx(0.0)
    unsigned = dict(row)
    stored = unsigned.pop("content_sha256")
    assert stored == movement_forecast_content_hash(unsigned)

    ledger = tmp_path / "movement.jsonl"
    assert append_movement_forecast_records(ledger, [row, row]) == 1
    assert append_movement_forecast_records(ledger, [row]) == 0
    loaded = load_movement_forecast_locks(ledger)
    assert len(loaded) == 1

    tampered = json.loads(ledger.read_text())
    tampered["forecasts"]["base_rf"]["movement"]["home"] += 0.01
    ledger.write_text(json.dumps(tampered) + "\n")
    with pytest.raises(ValueError, match="hash verification"):
        load_movement_forecast_locks(ledger)


def test_prospective_report_scores_later_common_book_move():
    lock = movement_lock()
    first = snapshot(
        "evt-1",
        "2026-09-04T12:00:00Z",
        [quote("a", 2.20, 3.40, 3.20), quote("b", 2.24, 3.36, 3.18)],
    )
    later = snapshot(
        "evt-1",
        "2026-09-05T12:00:00Z",
        [quote("a", 2.00, 3.55, 3.45), quote("b", 2.04, 3.50, 3.40)],
    )
    report = build_prospective_movement_report(
        [lock],
        [first, later],
        min_common_bookmakers=2,
    )
    assert report["matches_scored"] == 1
    assert report["coverage_rate"] == pytest.approx(1.0)
    assert report["events"][0]["common_bookmaker_count"] == 2
    assert report["events"][0]["actual_movement"]["home"] > 0.0
    assert (
        report["overall"]["base_rf"]["price_timing"][
            "fraction_selected_outcome_actually_shortened"
        ]
        == pytest.approx(1.0)
    )
    assert report["overall"]["zero_movement"]["direction_accuracy_nonzero_predictions"] is None
    assert report["overall"]["base_rf"]["mean_abs_error_per_outcome"] is not None
    assert report["overall"]["base_rf_mae_delta_vs_training_mean"] is not None


def test_report_refuses_to_score_without_two_common_books():
    lock = movement_lock()
    first = snapshot(
        "evt-1",
        "2026-09-04T12:00:00Z",
        [quote("a", 2.20, 3.40, 3.20), quote("b", 2.24, 3.36, 3.18)],
    )
    later = snapshot(
        "evt-1",
        "2026-09-05T12:00:00Z",
        [quote("a", 2.00, 3.55, 3.45), quote("c", 2.04, 3.50, 3.40)],
    )
    report = build_prospective_movement_report([lock], [first, later])
    assert report["matches_scored"] == 0
    assert report["skipped_insufficient_common_bookmakers"] == 1
    assert report["status"].startswith("awaiting_later_common_book")
