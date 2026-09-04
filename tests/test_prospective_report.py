import json
from pathlib import Path

import pytest

from football1.features import FeatureRow
from football1.prospective import make_prediction_record
from football1.prospective_report import THRESHOLDS, build_report
from football1.settlement import make_settlement_record


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


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_report_handles_unsettled_predictions_without_selecting_threshold(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    prediction = _prediction()
    _write_jsonl(ledger, [prediction])

    report = build_report(ledger, tmp_path / "missing-settlements.jsonl")
    assert report["prediction_records"] == 1
    assert report["settled_records"] == 0
    assert report["unsettled_records"] == 1
    assert report["probability_scoring"]["model_mean_log_loss"] is None
    assert [row["threshold"] for row in report["threshold_sensitivity"]] == list(THRESHOLDS)
    assert all(row["label"] == "sensitivity_only_not_strategy_selection" for row in report["threshold_sensitivity"])


def test_report_scores_settlement_and_fixed_threshold_panel(tmp_path: Path):
    prediction = _prediction()
    # Make the pre-recorded diagnostic exceed 2.5% but not 5%.
    prediction["model"]["max_predicted_ev"] = 0.04
    prediction["model"]["max_predicted_ev_outcome"] = "home"
    unsigned = dict(prediction)
    unsigned.pop("content_sha256")
    from football1.prospective import prediction_content_hash
    prediction["content_sha256"] = prediction_content_hash(unsigned)

    score = {
        "id": "event-1",
        "completed": True,
        "scores": [
            {"name": "Manchester United", "score": "2"},
            {"name": "Manchester City", "score": "1"},
        ],
        "last_update": "2026-09-05T16:00:00Z",
    }
    settlement = make_settlement_record(
        prediction,
        score,
        scores_retrieved_at_utc="2026-09-05T16:10:00+00:00",
    )
    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    _write_jsonl(ledger, [prediction])
    _write_jsonl(settlements, [settlement])

    report = build_report(ledger, settlements)
    assert report["settled_records"] == 1
    scoring = report["probability_scoring"]
    assert scoring["log_loss_delta_model_minus_market"] == pytest.approx(
        settlement["model_log_loss"] - settlement["market_log_loss"]
    )
    panel = {row["threshold"]: row for row in report["threshold_sensitivity"]}
    assert panel[0.025]["settled_qualifying_records"] == 1
    assert panel[0.025]["pnl_units"] == pytest.approx(2.5)
    assert panel[0.05]["settled_qualifying_records"] == 0


def test_report_rejects_settlement_linked_to_wrong_prediction_hash(tmp_path: Path):
    prediction = _prediction()
    settlement = make_settlement_record(
        prediction,
        {
            "id": "event-1",
            "completed": True,
            "scores": [
                {"name": "Manchester United", "score": "1"},
                {"name": "Manchester City", "score": "1"},
            ],
        },
        scores_retrieved_at_utc="2026-09-05T16:10:00+00:00",
    )
    settlement["prediction_content_sha256"] = "wrong"
    unsigned = dict(settlement)
    unsigned.pop("content_sha256")
    from football1.settlement import settlement_content_hash
    settlement["content_sha256"] = settlement_content_hash(unsigned)

    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    _write_jsonl(ledger, [prediction])
    _write_jsonl(settlements, [settlement])
    with pytest.raises(ValueError, match="prediction hash mismatch"):
        build_report(ledger, settlements)
