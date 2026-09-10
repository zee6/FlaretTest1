from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from football1.prospective import prediction_content_hash
from football1.prospective_error_batch_comparison import LOCKED_SNAPSHOT_UTC, build_report
from football1.settlement import settlement_content_hash


LABELS = ("home", "draw", "away")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _prediction(index: int, kickoff: str) -> dict:
    market = {"home": 0.40, "draw": 0.30, "away": 0.30}
    model = {"home": 0.42, "draw": 0.29, "away": 0.29}
    row = {
        "record_id": f"p{index}",
        "event_id": f"e{index}",
        "commence_time_utc": kickoff,
        "snapshot_retrieved_at_utc": LOCKED_SNAPSHOT_UTC,
        "home_team_canonical": f"Home {index}",
        "away_team_canonical": f"Away {index}",
        "market_anchor": {"probability": market},
        "model": {"probability": model},
    }
    row["content_sha256"] = prediction_content_hash(row)
    return row


def _brier(probability: dict[str, float], result: str) -> float:
    return sum((probability[label] - (1.0 if label == result else 0.0)) ** 2 for label in LABELS)


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


def _fixture_rows() -> tuple[list[dict], list[dict]]:
    first = [_prediction(i, f"2026-09-0{4 + (i % 3)}T14:00:00Z") for i in range(1, 11)]
    second = [_prediction(i, f"2026-09-{12 + (i % 3):02d}T14:00:00Z") for i in range(11, 21)]
    settlements = [_settlement(row, "draw" if i < 4 else "home") for i, row in enumerate(first)]
    return first + second, settlements


def test_batches_are_frozen_and_second_batch_stays_unobserved(tmp_path: Path) -> None:
    predictions, settlements = _fixture_rows()
    ledger = tmp_path / "ledger.jsonl"
    settlement_path = tmp_path / "settlements.jsonl"
    _write_jsonl(ledger, predictions)
    _write_jsonl(settlement_path, settlements)

    report = build_report(ledger, settlement_path)

    assert report["decision_weight"] == 0.0
    assert report["selection_rule"] is None
    assert report["model_change_allowed_from_report"] is False
    first, second = report["batches"]
    assert first["prediction_records"] == 10
    assert first["settled_records"] == 10
    assert first["evidence_stage"] == "prospective_complete"
    assert second["prediction_records"] == 10
    assert second["settled_records"] == 0
    assert second["evidence_stage"] == "prospective_frozen"
    assert report["comparison"]["available"] is False
    assert report["comparison"]["pass_fail_rule"] is None
    assert report["comparison"]["minimum_draw_count_rule"] is None


def test_later_snapshot_does_not_enter_frozen_batch(tmp_path: Path) -> None:
    predictions, settlements = _fixture_rows()
    extra = _prediction(99, "2026-09-12T14:00:00Z")
    extra["snapshot_retrieved_at_utc"] = "2026-09-10T10:00:00+00:00"
    unsigned = dict(extra)
    unsigned.pop("content_sha256")
    extra["content_sha256"] = prediction_content_hash(unsigned)
    predictions.append(extra)

    ledger = tmp_path / "ledger.jsonl"
    settlement_path = tmp_path / "settlements.jsonl"
    _write_jsonl(ledger, predictions)
    _write_jsonl(settlement_path, settlements)

    report = build_report(ledger, settlement_path)
    assert report["batches"][1]["prediction_records"] == 10
    assert "p99" not in report["batches"][1]["prediction_record_ids"]


def test_missing_frozen_prediction_fails_instead_of_changing_sample(tmp_path: Path) -> None:
    predictions, settlements = _fixture_rows()
    predictions.pop()
    ledger = tmp_path / "ledger.jsonl"
    settlement_path = tmp_path / "settlements.jsonl"
    _write_jsonl(ledger, predictions)
    _write_jsonl(settlement_path, settlements)

    with pytest.raises(ValueError, match="expected 10 predictions"):
        build_report(ledger, settlement_path)
