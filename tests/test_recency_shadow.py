from __future__ import annotations

import json
from pathlib import Path

import pytest

from football1.recency_shadow import append_shadow_records, build_shadow_records, content_hash


def _shadow_record(record_id: str = "shadow-a") -> dict:
    record = {
        "schema_version": 1,
        "record_id": record_id,
        "status": "recency_shadow_locked",
        "model_id": "test-shadow",
        "event_id": "event-a",
    }
    record["content_sha256"] = content_hash(record)
    return record


def test_content_hash_is_deterministic() -> None:
    record = {"b": 2, "a": 1}
    assert content_hash(record) == content_hash({"a": 1, "b": 2})


def test_append_shadow_records_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "shadow.jsonl"
    record = _shadow_record()
    assert append_shadow_records(path, [record]) == 1
    assert append_shadow_records(path, [record]) == 0
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_append_rejects_tampered_existing_ledger(tmp_path: Path) -> None:
    path = tmp_path / "shadow.jsonl"
    record = _shadow_record()
    append_shadow_records(path, [record])
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["event_id"] = "tampered"
    path.write_text(json.dumps(stored) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="content hash"):
        append_shadow_records(path, [])


def test_already_started_sources_are_never_backfilled(tmp_path: Path) -> None:
    source = [
        {
            "event_id": "old-event",
            "commence_time_utc": "2026-09-05T14:00:00Z",
            "snapshot_retrieved_at_utc": "2026-09-04T10:00:00Z",
        }
    ]
    records, metadata = build_shadow_records(
        tmp_path / "database-not-needed.sqlite",
        source,
        locked_at_utc="2026-09-07T20:00:00Z",
    )
    assert records == []
    assert metadata["created_records"] == 0
    assert metadata["skipped_already_started"] == 1
