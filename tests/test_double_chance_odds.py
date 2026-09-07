from __future__ import annotations

from football1.double_chance_odds import (
    build_double_chance_snapshot,
    select_events_from_h2h_snapshot,
    summarize_double_chance_event,
)


def sample_event() -> dict:
    return {
        "id": "evt-1",
        "sport_key": "soccer_epl",
        "commence_time": "2026-09-12T14:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "bookmakers": [
            {
                "key": "book_a",
                "title": "Book A",
                "markets": [
                    {
                        "key": "double_chance",
                        "outcomes": [
                            {"name": "Arsenal or Draw", "price": 1.35},
                            {"name": "Liverpool or Draw", "price": 1.75},
                            {"name": "Arsenal or Liverpool", "price": 1.28},
                        ],
                    }
                ],
            },
            {
                "key": "book_b",
                "title": "Book B",
                "markets": [
                    {
                        "key": "double_chance",
                        "outcomes": [
                            {"name": "Liverpool or Draw", "price": 1.80},
                            {"name": "Arsenal or Liverpool", "price": 1.25},
                            {"name": "Arsenal or Draw", "price": 1.38},
                        ],
                    }
                ],
            },
        ],
    }


def test_double_chance_summary_uses_named_binary_covers() -> None:
    summary = summarize_double_chance_event(sample_event())
    assert summary["complete_bookmaker_count"] == 2
    assert summary["best_decimal_odds"] == {"1X": 1.38, "X2": 1.80, "12": 1.28}
    assert summary["complete_bookmakers"] == ["Book A", "Book B"]


def test_incomplete_double_chance_book_is_excluded() -> None:
    event = sample_event()
    event["bookmakers"].append(
        {
            "key": "broken",
            "title": "Broken",
            "markets": [
                {
                    "key": "double_chance",
                    "outcomes": [
                        {"name": "Arsenal or Draw", "price": 1.40},
                        {"name": "Liverpool or Draw", "price": 1.85},
                    ],
                }
            ],
        }
    )
    summary = summarize_double_chance_event(event)
    assert summary["complete_bookmaker_count"] == 2
    assert "Broken" not in summary["complete_bookmakers"]


def test_event_selection_requires_explicit_opt_in() -> None:
    snapshot = {
        "summary": [
            {"event_id": "a"},
            {"event_id": "b"},
            {"event_id": "c"},
        ]
    }
    assert select_events_from_h2h_snapshot(snapshot) == []
    assert [x["event_id"] for x in select_events_from_h2h_snapshot(snapshot, max_events=2)] == ["a", "b"]
    assert [x["event_id"] for x in select_events_from_h2h_snapshot(snapshot, event_ids=["c"])] == ["c"]


def test_snapshot_records_quota_estimate_and_no_key() -> None:
    source = {"retrieved_at_utc": "2026-09-07T12:00:00+00:00"}
    snapshot = build_double_chance_snapshot(
        source_h2h_snapshot=source,
        event_results=[
            (
                sample_event(),
                {"requests_last": 1, "requests_used": 10, "requests_remaining": 490},
            )
        ],
        regions="uk,eu",
        odds_format="decimal",
        retrieved_at_utc="2026-09-07T12:05:00+00:00",
    )
    assert snapshot["estimated_max_usage_credits"] == 2
    assert snapshot["event_count"] == 1
    assert "apiKey" not in snapshot["request"]
