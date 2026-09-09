from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from football1.prospective import prediction_content_hash
from football1.prospective_error_anatomy import build_report
from football1.settlement import settlement_content_hash


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _prediction(record_id: str, event_id: str, market: dict[str, float], model: dict[str, float]) -> dict:
    row = {
        "record_id": record_id,
        "event_id": event_id,
        "commence_time_utc": "2026-09-01T14:00:00Z",
        "home_team_canonical": "Home",
        "away_team_canonical": "Away",
        "market_anchor": {"probability": market},
        "model": {"probability": model},
    }
    row["content_sha256"] = prediction_content_hash(row)
    return row


def _brier(probability: dict[str, float], result: str) -> float:
    return sum((probability[label] - (1.0 if label == result else 0.0)) ** 2 for label in ("home", "draw", "away"))


def _settlement(prediction: dict, result: str) -> dict:
    market = prediction["market_anchor"]["probability"]
    model = prediction["model"]["probability"]
    row = {
        "settlement_id": f"s-{prediction['record_id']}",
        "prediction_record_id": prediction["record_id"],
        "prediction_content_sha256": prediction["content_sha256"],
        "result": result,
        "market_log_loss": -math.log(market[result]),
        "model_log_loss": -math.log(model[result]),
        "market_brier": _brier(market, result),
        "model_brier": _brier(model, result),
    }
    row["content_sha256"] = settlement_content_hash(row)
    return row


def test_report_counts_help_and_harm_without_creating_rule(tmp_path: Path) -> None:
    helped = _prediction(
        "p1",
        "e1",
        {"home": 0.40, "draw": 0.30, "away": 0.30},
        {"home": 0.45, "draw": 0.28, "away": 0.27},
    )
    hurt = _prediction(
        "p2",
        "e2",
        {"home": 0.40, "draw": 0.30, "away": 0.30},
        {"home": 0.44, "draw": 0.31, "away": 0.25},
    )
    hurt["commence_time_utc"] = "2026-09-02T14:00:00Z"
    unsigned = dict(hurt)
    unsigned.pop("content_sha256")
    hurt["content_sha256"] = prediction_content_hash(unsigned)

    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    _write_jsonl(ledger, [helped, hurt])
    _write_jsonl(settlements, [_settlement(helped, "home"), _settlement(hurt, "away")])

    report = build_report(ledger, settlements)

    assert report["decision_weight"] == 0.0
    assert report["selection_rule"] is None
    assert report["model_change_allowed_from_report"] is False
    assert report["settled_matches"] == 2
    assert report["overall"]["model_helped_realized_outcome"] == 1
    assert report["overall"]["model_hurt_realized_outcome"] == 1
    rows = {row["event_id"]: row for row in report["matches"]}
    assert rows["e1"]["realized_outcome_probability_delta_model_minus_market"] == pytest.approx(0.05)
    assert rows["e1"]["log_loss_delta_model_minus_market"] < 0
    assert rows["e2"]["realized_outcome_probability_delta_model_minus_market"] == pytest.approx(-0.05)
    assert rows["e2"]["log_loss_delta_model_minus_market"] > 0


def test_report_rejects_settlement_metric_drift(tmp_path: Path) -> None:
    prediction = _prediction(
        "p1",
        "e1",
        {"home": 0.40, "draw": 0.30, "away": 0.30},
        {"home": 0.45, "draw": 0.28, "away": 0.27},
    )
    settlement = _settlement(prediction, "home")
    settlement["model_log_loss"] += 0.01
    unsigned = dict(settlement)
    unsigned.pop("content_sha256")
    settlement["content_sha256"] = settlement_content_hash(unsigned)

    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    _write_jsonl(ledger, [prediction])
    _write_jsonl(settlements, [settlement])

    with pytest.raises(ValueError, match="model_log_loss"):
        build_report(ledger, settlements)


def test_probability_moves_must_sum_to_zero(tmp_path: Path) -> None:
    prediction = _prediction(
        "p1",
        "e1",
        {"home": 0.40, "draw": 0.30, "away": 0.30},
        {"home": 0.45, "draw": 0.30, "away": 0.30},
    )
    ledger = tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    _write_jsonl(ledger, [prediction])
    _write_jsonl(settlements, [_settlement(prediction, "home")])

    with pytest.raises(ValueError, match="sum to one"):
        build_report(ledger, settlements)
