from __future__ import annotations

import json
from pathlib import Path

import pytest

from football1.draw_possibility_prospective_report import build_report
from football1.draw_possibility_shadow import content_hash as shadow_content_hash
from football1.prospective import prediction_content_hash
from football1.settlement import settlement_content_hash


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _prediction(record_id: str, event_id: str, pdraw: float, draw_odds: float) -> dict:
    remaining = 1.0 - pdraw
    row = {
        "record_id": record_id,
        "event_id": event_id,
        "market_anchor": {
            "probability": {"home": remaining / 2, "draw": pdraw, "away": remaining / 2},
            "best_decimal_odds": {"home": 2.5, "draw": draw_odds, "away": 2.5},
        },
    }
    row["content_sha256"] = prediction_content_hash(row)
    return row


def _shadow(prediction: dict, possibility: float, gap: float, flags: dict[str, bool]) -> dict:
    row = {
        "record_id": f"shadow-{prediction['event_id']}",
        "decision_weight": 0.0,
        "event_id": prediction["event_id"],
        "commence_time_utc": "2026-09-12T14:00:00Z",
        "teams": {"home": f"H-{prediction['event_id']}", "away": f"A-{prediction['event_id']}"},
        "source_prediction": {
            "record_id": prediction["record_id"],
            "content_sha256": prediction["content_sha256"],
        },
        "market_probability": prediction["market_anchor"]["probability"],
        "draw_possibility": {
            "balance_percentile_0_to_100": possibility,
            "home_away_probability_gap": gap,
            "is_probability": False,
            "fixed_predeclared_balance_flags": flags,
        },
    }
    row["content_sha256"] = shadow_content_hash(row)
    return row


def _settlement(prediction: dict, result: str) -> dict:
    row = {
        "settlement_id": f"settlement-{prediction['event_id']}",
        "prediction_record_id": prediction["record_id"],
        "prediction_content_sha256": prediction["content_sha256"],
        "event_id": prediction["event_id"],
        "result": result,
    }
    row["content_sha256"] = settlement_content_hash(row)
    return row


def test_report_freezes_top_two_and_scores_draw_pnl(tmp_path: Path) -> None:
    predictions = [
        _prediction("p1", "e1", 0.27, 3.6),
        _prediction("p2", "e2", 0.29, 3.4),
        _prediction("p3", "e3", 0.31, 3.2),
    ]
    shadows = [
        _shadow(predictions[0], 99.0, 0.01, {"within_2pp": True, "within_5pp": True, "within_10pp": True}),
        _shadow(predictions[1], 95.0, 0.03, {"within_2pp": False, "within_5pp": True, "within_10pp": True}),
        _shadow(predictions[2], 70.0, 0.12, {"within_2pp": False, "within_5pp": False, "within_10pp": False}),
    ]
    settlements = [
        _settlement(predictions[0], "draw"),
        _settlement(predictions[1], "home"),
        _settlement(predictions[2], "draw"),
    ]
    shadow_path, ledger_path, settlement_path = tmp_path / "shadow.jsonl", tmp_path / "ledger.jsonl", tmp_path / "settlements.jsonl"
    _write(shadow_path, shadows)
    _write(ledger_path, predictions)
    _write(settlement_path, settlements)

    report = build_report(shadow_path, ledger_path, settlement_path)
    top2 = report["predeclared_rank_summaries"]["top_2_draw_possibility"]
    assert [event["event_id"] for event in top2["events"]] == ["e1", "e2"]
    assert top2["complete"] is True
    assert top2["draws"] == 1
    assert top2["draw_rate"] == pytest.approx(0.5)
    assert top2["gross_draw_pnl_units_at_recorded_best"] == pytest.approx(1.6)


def test_incomplete_top_two_does_not_report_final_rate_or_pnl(tmp_path: Path) -> None:
    predictions = [_prediction("p1", "e1", 0.27, 3.6), _prediction("p2", "e2", 0.29, 3.4)]
    shadows = [
        _shadow(predictions[0], 99.0, 0.01, {"within_2pp": True, "within_5pp": True, "within_10pp": True}),
        _shadow(predictions[1], 95.0, 0.03, {"within_2pp": False, "within_5pp": True, "within_10pp": True}),
    ]
    shadow_path, ledger_path, settlement_path = tmp_path / "shadow.jsonl", tmp_path / "ledger.jsonl", tmp_path / "settlements.jsonl"
    _write(shadow_path, shadows)
    _write(ledger_path, predictions)
    _write(settlement_path, [_settlement(predictions[0], "draw")])

    report = build_report(shadow_path, ledger_path, settlement_path)
    top2 = report["predeclared_rank_summaries"]["top_2_draw_possibility"]
    assert top2["settled"] == 1
    assert top2["complete"] is False
    assert top2["draw_rate"] is None
    assert top2["gross_draw_pnl_units_at_recorded_best"] is None


def test_shadow_prediction_hash_link_is_enforced(tmp_path: Path) -> None:
    prediction = _prediction("p1", "e1", 0.27, 3.6)
    shadow = _shadow(prediction, 99.0, 0.01, {"within_2pp": True, "within_5pp": True, "within_10pp": True})
    shadow["source_prediction"]["content_sha256"] = "wrong"
    shadow.pop("content_sha256")
    shadow["content_sha256"] = shadow_content_hash(shadow)
    shadow_path, ledger_path, settlement_path = tmp_path / "shadow.jsonl", tmp_path / "ledger.jsonl", tmp_path / "settlements.jsonl"
    _write(shadow_path, [shadow])
    _write(ledger_path, [prediction])
    _write(settlement_path, [])

    with pytest.raises(ValueError, match="prediction hash mismatch"):
        build_report(shadow_path, ledger_path, settlement_path)
