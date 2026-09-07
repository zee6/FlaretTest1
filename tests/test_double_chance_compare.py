from __future__ import annotations

import pytest

from football1.double_chance_compare import compare_event, compare_snapshots


def prediction_record() -> dict:
    return {
        "record_id": "lock-1",
        "event_id": "evt-1",
        "status": "prediction_locked",
        "commence_time_utc": "2026-09-12T14:00:00Z",
        "snapshot_retrieved_at_utc": "2026-09-07T12:00:00Z",
        "home_team_provider": "Arsenal",
        "away_team_provider": "Liverpool",
        "market_anchor": {
            "probability": {"home": 0.45, "draw": 0.27, "away": 0.28},
            "best_decimal_odds": {"home": 2.10, "draw": 3.80, "away": 3.70},
        },
        "model": {
            "probability": {"home": 0.42, "draw": 0.30, "away": 0.28},
        },
        "features": {"elo_diff": 15.0},
    }


def double_chance_summary() -> dict:
    return {
        "event_id": "evt-1",
        "complete_bookmaker_count": 4,
        "best_decimal_odds": {"1X": 1.45, "X2": 1.80, "12": 1.30},
    }


def test_compare_event_uses_actual_and_synthetic_prices() -> None:
    report = compare_event(prediction_record(), double_chance_summary())
    one_x = report["covers"]["1X"]
    x_two = report["covers"]["X2"]

    assert one_x["model_probability"] == pytest.approx(0.72)
    assert one_x["quoted_double_chance_odds"] == pytest.approx(1.45)
    assert one_x["model_ev_at_quoted_double_chance"] == pytest.approx(0.044)
    assert one_x["synthetic_dutched_odds"] != pytest.approx(1.45)

    assert x_two["model_probability"] == pytest.approx(0.58)
    assert x_two["model_ev_at_quoted_double_chance"] == pytest.approx(0.044)
    assert report["decision_weight"] == 0.0
    assert report["betting_threshold"] is None


def test_compare_snapshots_joins_only_common_event_ids() -> None:
    other = dict(prediction_record())
    other["record_id"] = "lock-2"
    other["event_id"] = "evt-2"
    snapshot = {
        "retrieved_at_utc": "2026-09-07T12:05:00Z",
        "summary": [double_chance_summary()],
    }

    report = compare_snapshots([prediction_record(), other], snapshot)
    assert report["prediction_event_count"] == 2
    assert report["double_chance_event_count"] == 1
    assert report["common_event_count"] == 1
    assert report["rows"][0]["event_id"] == "evt-1"
