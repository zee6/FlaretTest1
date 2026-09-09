from __future__ import annotations

import json
from pathlib import Path

import pytest

from football1.prospective import prediction_content_hash
from football1.recency_prospective_report import build_report
from football1.recency_shadow import content_hash as shadow_content_hash
from football1.settlement import settlement_content_hash


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _prediction(event_id: str, record_id: str, market: dict[str, float], model: dict[str, float]) -> dict:
    row = {
        "record_id": record_id,
        "event_id": event_id,
        "market_anchor": {"probability": market},
        "model": {"probability": model},
    }
    row["content_sha256"] = prediction_content_hash(row)
    return row


def _settlement(prediction: dict, result: str) -> dict:
    row = {
        "settlement_id": f"settle-{prediction['event_id']}",
        "prediction_record_id": prediction["record_id"],
        "prediction_content_sha256": prediction["content_sha256"],
        "event_id": prediction["event_id"],
        "result": result,
    }
    row["content_sha256"] = settlement_content_hash(row)
    return row


def _shadow(prediction: dict, model_id: str, half_life: float, probability: dict[str, float]) -> dict:
    row = {
        "record_id": f"{model_id}-{prediction['event_id']}",
        "model_id": model_id,
        "decision_weight": 0.0,
        "event_id": prediction["event_id"],
        "shadow_locked_at_utc": "2026-09-09T09:00:00Z",
        "source_prediction": {
            "record_id": prediction["record_id"],
            "content_sha256": prediction["content_sha256"],
        },
        "market_probability": prediction["market_anchor"]["probability"],
        "equal_weight_probability": prediction["model"]["probability"],
        "recency_probability": probability,
        "recency_policy": {"half_life_days": half_life},
    }
    row["content_sha256"] = shadow_content_hash(row)
    return row


def test_scores_only_strict_common_settled_events(tmp_path: Path) -> None:
    p1 = _prediction(
        "e1",
        "p1",
        {"home": 0.50, "draw": 0.25, "away": 0.25},
        {"home": 0.52, "draw": 0.24, "away": 0.24},
    )
    p2 = _prediction(
        "e2",
        "p2",
        {"home": 0.40, "draw": 0.30, "away": 0.30},
        {"home": 0.41, "draw": 0.29, "away": 0.30},
    )
    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    s30 = tmp_path / "s30.jsonl"
    s15 = tmp_path / "s15.jsonl"
    _write_jsonl(ledger, [p1, p2])
    _write_jsonl(settlements, [_settlement(p1, "home")])
    _write_jsonl(
        s30,
        [
            _shadow(p1, "recency30", 30.0, {"home": 0.53, "draw": 0.235, "away": 0.235}),
            _shadow(p2, "recency30", 30.0, {"home": 0.42, "draw": 0.29, "away": 0.29}),
        ],
    )
    _write_jsonl(
        s15,
        [
            _shadow(p1, "recency15", 15.0, {"home": 0.54, "draw": 0.23, "away": 0.23}),
            _shadow(p2, "recency15", 15.0, {"home": 0.43, "draw": 0.285, "away": 0.285}),
        ],
    )

    report = build_report(ledger, settlements, [s30, s15])
    assert report["shadow_event_count"] == 2
    assert report["settled_common_event_count"] == 1
    assert report["unsettled_shadow_event_count"] == 1
    assert report["common_event_ids"] == ["e1"]
    assert report["models"]["market_consensus"]["mean_log_loss"] == pytest.approx(-__import__("math").log(0.50))
    assert report["models"]["recency15"]["mean_log_loss"] < report["models"]["recency30"]["mean_log_loss"]
    assert report["models"]["recency30"]["log_loss_delta_vs_market"] is not None


def test_zero_settled_common_events_is_valid_pre_match_state(tmp_path: Path) -> None:
    p1 = _prediction(
        "e1",
        "p1",
        {"home": 0.50, "draw": 0.25, "away": 0.25},
        {"home": 0.52, "draw": 0.24, "away": 0.24},
    )
    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    s30 = tmp_path / "s30.jsonl"
    s15 = tmp_path / "s15.jsonl"
    _write_jsonl(ledger, [p1])
    _write_jsonl(settlements, [])
    _write_jsonl(s30, [_shadow(p1, "recency30", 30.0, {"home": 0.53, "draw": 0.235, "away": 0.235})])
    _write_jsonl(s15, [_shadow(p1, "recency15", 15.0, {"home": 0.54, "draw": 0.23, "away": 0.23})])

    report = build_report(ledger, settlements, [s30, s15])
    assert report["settled_common_event_count"] == 0
    assert report["models"]["market_consensus"]["mean_log_loss"] is None


def test_shadow_source_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    p1 = _prediction(
        "e1",
        "p1",
        {"home": 0.50, "draw": 0.25, "away": 0.25},
        {"home": 0.52, "draw": 0.24, "away": 0.24},
    )
    bad = _shadow(p1, "recency30", 30.0, {"home": 0.53, "draw": 0.235, "away": 0.235})
    bad["source_prediction"]["content_sha256"] = "wrong"
    bad.pop("content_sha256")
    bad["content_sha256"] = shadow_content_hash(bad)

    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    shadow = tmp_path / "shadow.jsonl"
    _write_jsonl(ledger, [p1])
    _write_jsonl(settlements, [])
    _write_jsonl(shadow, [bad])

    with pytest.raises(ValueError, match="source hash mismatch"):
        build_report(ledger, settlements, [shadow])


def test_shadow_files_must_have_identical_event_sets(tmp_path: Path) -> None:
    p1 = _prediction(
        "e1",
        "p1",
        {"home": 0.50, "draw": 0.25, "away": 0.25},
        {"home": 0.52, "draw": 0.24, "away": 0.24},
    )
    p2 = _prediction(
        "e2",
        "p2",
        {"home": 0.40, "draw": 0.30, "away": 0.30},
        {"home": 0.41, "draw": 0.29, "away": 0.30},
    )
    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    s30 = tmp_path / "s30.jsonl"
    s15 = tmp_path / "s15.jsonl"
    _write_jsonl(ledger, [p1, p2])
    _write_jsonl(settlements, [])
    _write_jsonl(s30, [_shadow(p1, "recency30", 30.0, {"home": 0.53, "draw": 0.235, "away": 0.235})])
    _write_jsonl(s15, [_shadow(p2, "recency15", 15.0, {"home": 0.43, "draw": 0.285, "away": 0.285})])

    with pytest.raises(ValueError, match="identical event sets"):
        build_report(ledger, settlements, [s30, s15])
