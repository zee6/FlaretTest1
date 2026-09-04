import json
from pathlib import Path

import pytest

from football1.features import FeatureRow
from football1.prospective import make_prediction_record
from football1.settlement import (
    append_settlements,
    make_settlement_record,
    settlement_content_hash,
    settle_from_scores,
)


def _prediction() -> dict:
    feature = FeatureRow(
        match_id="event-1",
        season_start_year=2026,
        match_date="2026-09-05",
        home_team="Man United",
        away_team="Man City",
        result="",
        elo_diff=0.0,
        ppg5_diff=0.0,
        gf5_diff=0.0,
        ga5_diff=0.0,
        shots5_diff=0.0,
        shots_allowed5_diff=0.0,
        sot5_diff=0.0,
        sot_allowed5_diff=0.0,
        ppg10_diff=0.0,
        gf10_diff=0.0,
        ga10_diff=0.0,
        rest_days_diff=0.0,
        log_prior_games_home=5.0,
        log_prior_games_away=5.0,
        b365_home=None,
        b365_draw=None,
        b365_away=None,
    )
    event = {
        "event_id": "event-1",
        "commence_time": "2026-09-05T14:00:00Z",
        "home_team": "Manchester United",
        "away_team": "Manchester City",
        "complete_h2h_bookmaker_count": 20,
        "consensus_fair_probability": {"home": 0.30, "draw": 0.25, "away": 0.45},
        "best_decimal_odds": {"home": 3.5, "draw": 4.1, "away": 2.3},
    }
    return make_prediction_record(
        event=event,
        snapshot_retrieved_at_utc="2026-09-04T09:00:00+00:00",
        model_probability=(0.31, 0.24, 0.45),
        feature_row=feature,
        training_matches=5000,
        historical_data_cutoff="2026-08-31",
    )


def _score_event() -> dict:
    return {
        "id": "event-1",
        "completed": True,
        "home_team": "Manchester United",
        "away_team": "Manchester City",
        "scores": [
            {"name": "Manchester United", "score": "2"},
            {"name": "Manchester City", "score": "1"},
        ],
        "last_update": "2026-09-05T16:10:00Z",
    }


def test_settlement_preserves_prediction_reference_and_scores_all_outcomes():
    prediction = _prediction()
    record = make_settlement_record(
        prediction,
        _score_event(),
        scores_retrieved_at_utc="2026-09-05T16:15:00+00:00",
    )
    assert record["prediction_record_id"] == prediction["record_id"]
    assert record["prediction_content_sha256"] == prediction["content_sha256"]
    assert record["result"] == "home"
    assert record["home_score"] == 2
    assert record["away_score"] == 1
    assert record["unit_pnl_if_bet_at_recorded_best_odds"] == {
        "home": 2.5,
        "draw": -1.0,
        "away": -1.0,
    }
    assert record["strategy_threshold"] is None
    unsigned = dict(record)
    stored = unsigned.pop("content_sha256")
    assert stored == settlement_content_hash(unsigned)


def test_uncompleted_score_cannot_settle():
    score = _score_event()
    score["completed"] = False
    with pytest.raises(ValueError, match="not marked completed"):
        make_settlement_record(
            _prediction(),
            score,
            scores_retrieved_at_utc="2026-09-05T16:15:00+00:00",
        )


def test_settle_from_scores_is_idempotent_by_prediction_record():
    prediction = _prediction()
    records = settle_from_scores(
        [prediction],
        [],
        [_score_event()],
        scores_retrieved_at_utc="2026-09-05T16:15:00+00:00",
    )
    assert len(records) == 1
    second = settle_from_scores(
        [prediction],
        records,
        [_score_event()],
        scores_retrieved_at_utc="2026-09-05T16:20:00+00:00",
    )
    assert second == []


def test_append_settlements_rejects_tampering(tmp_path: Path):
    path = tmp_path / "settlements.jsonl"
    record = make_settlement_record(
        _prediction(),
        _score_event(),
        scores_retrieved_at_utc="2026-09-05T16:15:00+00:00",
    )
    assert append_settlements(path, [record]) == 1
    assert append_settlements(path, [record]) == 0

    item = json.loads(path.read_text(encoding="utf-8"))
    item["home_score"] = 99
    path.write_text(json.dumps(item) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash verification"):
        append_settlements(path, [])
