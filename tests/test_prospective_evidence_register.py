from __future__ import annotations

import json
from pathlib import Path

import pytest

from football1.prospective import prediction_content_hash
from football1.prospective_consensus_movement import movement_forecast_content_hash
from football1.prospective_evidence_register import ARTIFACT_PINS, LANE_IDS, _stage, build_register
from football1.settlement import settlement_content_hash


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _prediction() -> dict:
    row = {
        "record_id": "prediction-1",
        "event_id": "event-1",
        "model": {"id": "fixed_market_offset_football_slant_v1"},
    }
    row["content_sha256"] = prediction_content_hash(row)
    return row


def _settlement(prediction: dict) -> dict:
    row = {
        "settlement_id": "settlement-1",
        "prediction_record_id": prediction["record_id"],
        "prediction_content_sha256": prediction["content_sha256"],
    }
    row["content_sha256"] = settlement_content_hash(row)
    return row


def _movement(*, decision_weight: float = 0.0) -> dict:
    row = {
        "record_id": "movement-1",
        "decision_weight": decision_weight,
        "model_suite_id": "movement-suite-v1",
    }
    row["content_sha256"] = movement_forecast_content_hash(row)
    return row


def test_stage_transitions_are_chronological_not_quality_labels() -> None:
    assert _stage(10, 0) == "prospective_frozen"
    assert _stage(10, 3) == "prospective_partial"
    assert _stage(10, 10) == "prospective_complete"
    with pytest.raises(ValueError):
        _stage(10, 11)


def test_register_has_no_master_score_or_promotion(tmp_path: Path) -> None:
    prediction = _prediction()
    settlement = _settlement(prediction)
    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    movement = tmp_path / "movement.jsonl"
    _write_jsonl(ledger, [prediction])
    _write_jsonl(settlements, [settlement])
    _write_jsonl(movement, [_movement()])

    register = build_register(ledger, settlements, movement)

    assert register["master_score"] is None
    assert register["decision_weight"] == 0.0
    assert "prohibited" in register["aggregation_policy"]
    assert tuple(row["lane_id"] for row in register["lanes"]) == LANE_IDS
    assert all(row["decision_weight"] == 0.0 for row in register["lanes"])
    assert all(row["promotion_eligible_from_current_register"] is False for row in register["lanes"])
    draw = next(row for row in register["lanes"] if row["lane_id"] == "draw_possibility")
    assert any("nap" in note for note in draw["notes"])
    assert "interpret_internal_0_to_100_rank_as_probability_or_recommendation" in draw["prohibited_changes"]


def test_loaded_shadow_reports_only_change_stage_and_observed_state(tmp_path: Path) -> None:
    prediction = _prediction()
    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    movement = tmp_path / "movement.jsonl"
    _write_jsonl(ledger, [prediction])
    _write_jsonl(settlements, [])
    _write_jsonl(movement, [_movement()])

    recency_report = {
        "shadow_event_count": 10,
        "settled_common_event_count": 0,
        "unsettled_shadow_event_count": 10,
        "shadow_files": [
            {"model_id": "fixed_market_offset_football_slant_v1_recency_30d_prospective_shadow"},
            {"model_id": "fixed_market_offset_football_slant_v1_recency_15d_prospective_shadow"},
        ],
    }
    draw_report = {
        "shadow_records": 10,
        "settled_shadow_records": 0,
        "predeclared_rank_summaries": {
            "top_2_draw_possibility": {
                "events": [
                    {"home": "Bournemouth", "away": "Brentford", "rank": 1, "possibility": 99.2},
                    {"home": "Leeds", "away": "Newcastle", "rank": 2, "possibility": 95.0},
                ]
            }
        },
    }

    register = build_register(
        ledger,
        settlements,
        movement,
        recency_report=recency_report,
        draw_report=draw_report,
    )
    recency = next(row for row in register["lanes"] if row["lane_id"] == "general_recency")
    draw = next(row for row in register["lanes"] if row["lane_id"] == "draw_possibility")
    assert recency["evidence_stage"] == "prospective_frozen"
    assert draw["evidence_stage"] == "prospective_frozen"
    assert draw["state"]["top_2_frozen_events"][0]["home"] == "Bournemouth"
    assert draw["state"]["top_2_frozen_events"][0]["internal_balance_rank_0_to_100"] == 99.2
    assert draw["promotion_eligible_from_current_register"] is False


def test_register_rejects_nonzero_movement_decision_weight(tmp_path: Path) -> None:
    prediction = _prediction()
    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    movement = tmp_path / "movement.jsonl"
    _write_jsonl(ledger, [prediction])
    _write_jsonl(settlements, [])
    _write_jsonl(movement, [_movement(decision_weight=1.0)])

    with pytest.raises(ValueError, match="zero decision weight"):
        build_register(ledger, settlements, movement)


def test_artifact_pins_are_explicit_and_distinct() -> None:
    assert set(ARTIFACT_PINS) == {
        "recency_30d_shadow",
        "recency_15d_shadow",
        "draw_possibility_shadow",
    }
    assert len({row["sha256"] for row in ARTIFACT_PINS.values()}) == 3
    assert all(len(row["sha256"]) == 64 for row in ARTIFACT_PINS.values())
