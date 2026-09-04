from __future__ import annotations

import json
from pathlib import Path

import pytest

from football1.market_movement_observer import (
    build_market_movement_report,
    load_odds_snapshots,
    load_prediction_locks,
)
from football1.odds_archive import odds_record_hash
from football1.prospective import prediction_content_hash


def _prediction(
    *,
    locked_at: str = "2026-09-04T09:00:00Z",
    market: tuple[float, float, float] = (0.50, 0.30, 0.20),
    model: tuple[float, float, float] = (0.55, 0.28, 0.17),
) -> dict:
    row = {
        "record_id": f"prediction-{locked_at}",
        "status": "prediction_locked",
        "event_id": "event-1",
        "commence_time_utc": "2026-09-05T14:00:00Z",
        "snapshot_retrieved_at_utc": locked_at,
        "home_team_provider": "Home",
        "away_team_provider": "Away",
        "market_anchor": {
            "probability": dict(zip(("home", "draw", "away"), market)),
        },
        "model": {
            "id": "model-v1",
            "probability": dict(zip(("home", "draw", "away"), model)),
        },
    }
    row["content_sha256"] = prediction_content_hash(row)
    return row


def _odds(
    retrieved_at: str,
    probability: tuple[float, float, float],
    *,
    kickoff: str = "2026-09-05T14:00:00Z",
) -> dict:
    row = {
        "record_id": f"odds-{retrieved_at}",
        "status": "pre_kickoff_odds_snapshot",
        "event_id": "event-1",
        "commence_time_utc": kickoff,
        "retrieved_at_utc": retrieved_at,
        "consensus_fair_probability": dict(zip(("home", "draw", "away"), probability)),
        "fair_probability_dispersion": {"home": 0.01, "draw": 0.02, "away": 0.03},
    }
    row["content_sha256"] = odds_record_hash(row)
    return row


def test_report_waits_when_no_later_snapshot_exists() -> None:
    report = build_market_movement_report([_prediction()], [])
    assert report["status"] == "awaiting_later_price_snapshots_zero_decision_weight"
    assert report["locked_predictions"] == 1
    assert report["matches_with_later_market_snapshot"] == 0
    assert report["overall"]["fraction_market_closer_to_football1"] is None


def test_later_market_move_toward_model_is_measured_without_changing_lock() -> None:
    prediction = _prediction()
    later = _odds("2026-09-04T12:00:00Z", (0.53, 0.29, 0.18))
    report = build_market_movement_report([prediction], [later])
    event = report["events"][0]

    assert report["status"] == "prospective_market_movement_observer_zero_decision_weight"
    assert report["coverage_rate"] == 1.0
    assert event["locked_market_probability"]["home"] == pytest.approx(0.50)
    assert event["model_probability"]["home"] == pytest.approx(0.55)
    assert event["latest_market_probability"]["home"] == pytest.approx(0.53)
    assert event["market_move"]["home"] == pytest.approx(0.03)
    assert event["market_is_closer_to_model"] is True
    assert event["movement_direction_aligns_with_model"] is True
    assert event["model_call"] == "home"
    assert event["model_call_market_moved_toward"] is True
    assert report["overall"]["fraction_market_closer_to_football1"] == 1.0


def test_only_latest_strictly_post_lock_pre_kickoff_snapshot_is_used() -> None:
    prediction = _prediction()
    before_lock = _odds("2026-09-04T08:00:00Z", (0.60, 0.25, 0.15))
    first_later = _odds("2026-09-04T10:00:00Z", (0.51, 0.30, 0.19))
    latest_later = _odds("2026-09-05T13:00:00Z", (0.54, 0.28, 0.18))
    after_kickoff = _odds(
        "2026-09-05T15:00:00Z",
        (0.70, 0.20, 0.10),
        kickoff="2026-09-05T14:00:00Z",
    )
    report = build_market_movement_report(
        [prediction], [before_lock, first_later, after_kickoff, latest_later]
    )
    event = report["events"][0]
    assert event["later_snapshots"] == 2
    assert event["latest_market_at_utc"] == "2026-09-05T13:00:00Z"
    assert event["latest_market_probability"]["home"] == pytest.approx(0.54)


def test_earliest_prediction_lock_wins_if_legacy_duplicates_exist() -> None:
    first = _prediction(
        locked_at="2026-09-04T09:00:00Z",
        model=(0.55, 0.28, 0.17),
    )
    accidental_later_lock = _prediction(
        locked_at="2026-09-04T10:00:00Z",
        model=(0.40, 0.35, 0.25),
    )
    later_market = _odds("2026-09-04T12:00:00Z", (0.53, 0.29, 0.18))
    report = build_market_movement_report(
        [accidental_later_lock, first], [later_market]
    )
    assert report["locked_predictions"] == 1
    assert report["events"][0]["locked_at_utc"] == "2026-09-04T09:00:00Z"
    assert report["events"][0]["model_probability"]["home"] == pytest.approx(0.55)


def test_jsonl_loaders_reject_tampering(tmp_path: Path) -> None:
    prediction = _prediction()
    odds = _odds("2026-09-04T12:00:00Z", (0.53, 0.29, 0.18))
    ledger = tmp_path / "ledger.jsonl"
    archive = tmp_path / "odds.jsonl"
    ledger.write_text(json.dumps(prediction) + "\n", encoding="utf-8")
    archive.write_text(json.dumps(odds) + "\n", encoding="utf-8")

    assert len(load_prediction_locks(ledger)) == 1
    assert len(load_odds_snapshots(archive)) == 1

    tampered = dict(odds)
    tampered["consensus_fair_probability"] = {"home": 0.7, "draw": 0.2, "away": 0.1}
    archive.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash verification"):
        load_odds_snapshots(archive)
