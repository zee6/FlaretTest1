from __future__ import annotations

import json
from pathlib import Path

import pytest

from football1.odds_archive import append_odds_records, normalize_snapshot, odds_record_hash


def _snapshot() -> dict:
    return {
        "provider": "the-odds-api",
        "sport_key": "soccer_epl",
        "retrieved_at_utc": "2026-09-04T10:00:00+00:00",
        "request": {"regions": "uk", "markets": "h2h", "odds_format": "decimal"},
        "events": [
            {
                "id": "future",
                "commence_time": "2026-09-05T14:00:00Z",
                "home_team": "Home",
                "away_team": "Away",
                "bookmakers": [
                    {
                        "key": "a",
                        "title": "Book A",
                        "last_update": "2026-09-04T09:59:00Z",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "Home", "price": 2.0},
                            {"name": "Draw", "price": 3.5},
                            {"name": "Away", "price": 4.0},
                        ]}],
                    },
                    {
                        "key": "b",
                        "title": "Book B",
                        "last_update": "2026-09-04T09:58:00Z",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "Home", "price": 2.1},
                            {"name": "Draw", "price": 3.4},
                            {"name": "Away", "price": 3.9},
                        ]}],
                    },
                    {
                        "key": "incomplete",
                        "title": "Incomplete",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "Home", "price": 2.0},
                            {"name": "Away", "price": 4.0},
                        ]}],
                    },
                ],
            },
            {
                "id": "started",
                "commence_time": "2026-09-04T09:00:00Z",
                "home_team": "Old Home",
                "away_team": "Old Away",
                "bookmakers": [],
            },
        ],
    }


def test_normalize_snapshot_keeps_complete_future_quotes_only() -> None:
    records = normalize_snapshot(_snapshot())
    assert len(records) == 1
    row = records[0]
    assert row["event_id"] == "future"
    assert row["complete_h2h_bookmaker_count"] == 2
    assert [q["bookmaker_key"] for q in row["bookmakers"]] == ["a", "b"]
    assert row["best_decimal_odds"] == {"home": 2.1, "draw": 3.5, "away": 4.0}
    assert row["fair_probability_dispersion"]["home"] is not None
    assert row["content_sha256"] == odds_record_hash(
        {k: v for k, v in row.items() if k != "content_sha256"}
    )


def test_append_is_duplicate_safe_and_verifies_hashes(tmp_path: Path) -> None:
    record = normalize_snapshot(_snapshot())[0]
    path = tmp_path / "odds.jsonl"
    assert append_odds_records(path, [record]) == 1
    assert append_odds_records(path, [record]) == 0
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 1

    rows[0]["home_team"] = "Tampered"
    path.write_text(json.dumps(rows[0]) + "\n")
    with pytest.raises(ValueError, match="hash verification"):
        append_odds_records(path, [])


def test_snapshot_id_changes_with_retrieval_time() -> None:
    first = _snapshot()
    second = _snapshot()
    second["retrieved_at_utc"] = "2026-09-04T10:05:00+00:00"
    assert normalize_snapshot(first)[0]["record_id"] != normalize_snapshot(second)[0]["record_id"]
