from __future__ import annotations

import json
from pathlib import Path

import pytest

from football1.draw_possibility_shadow import (
    append_shadow_records,
    build_shadow_records,
    content_hash,
    possibility_percentile,
)


def _shadow_record(record_id: str = "shadow-a") -> dict:
    row = {
        "schema_version": 1,
        "record_id": record_id,
        "status": "draw_possibility_shadow_locked",
        "model_id": "test",
        "decision_weight": 0.0,
    }
    row["content_sha256"] = content_hash(row)
    return row


def test_possibility_percentile_is_higher_for_more_balanced_match() -> None:
    historical = [0.01, 0.03, 0.05, 0.10, 0.20]
    assert possibility_percentile(0.02, historical) > possibility_percentile(0.08, historical)
    assert possibility_percentile(0.0, historical) == pytest.approx(100.0)


def test_possibility_percentile_is_not_a_probability_contract() -> None:
    historical = [0.02, 0.10, 0.20, 0.30]
    score = possibility_percentile(0.10, historical)
    assert score == pytest.approx(75.0)
    assert score > 1.0


def test_already_started_sources_are_never_backfilled(tmp_path: Path) -> None:
    source = [{"event_id": "old", "commence_time_utc": "2026-09-05T14:00:00Z"}]
    records, metadata = build_shadow_records(
        tmp_path / "db-not-needed.sqlite",
        source,
        locked_at_utc="2026-09-09T12:00:00Z",
    )
    assert records == []
    assert metadata["created_records"] == 0
    assert metadata["skipped_already_started"] == 1
    assert metadata["decision_weight"] == 0.0


def test_append_is_idempotent_and_rejects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "shadow.jsonl"
    row = _shadow_record()
    assert append_shadow_records(path, [row]) == 1
    assert append_shadow_records(path, [row]) == 0

    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["decision_weight"] = 1.0
    path.write_text(json.dumps(stored) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="content hash"):
        append_shadow_records(path, [])
