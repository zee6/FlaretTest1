from __future__ import annotations

import pytest

from football1.slate_rankings import build_slate_rankings


def _record(
    *,
    record_id: str,
    event_id: str,
    home: str,
    away: str,
    model: tuple[float, float, float],
    market: tuple[float, float, float],
    odds: tuple[float, float, float],
    elo_diff: float,
    retrieved: str = "2026-09-04T09:00:00Z",
) -> dict:
    return {
        "record_id": record_id,
        "event_id": event_id,
        "status": "prediction_locked",
        "commence_time_utc": "2026-09-10T14:00:00Z",
        "snapshot_retrieved_at_utc": retrieved,
        "home_team_provider": home,
        "away_team_provider": away,
        "market_anchor": {
            "probability": {"home": market[0], "draw": market[1], "away": market[2]},
            "best_decimal_odds": {"home": odds[0], "draw": odds[1], "away": odds[2]},
        },
        "model": {
            "probability": {"home": model[0], "draw": model[1], "away": model[2]},
        },
        "features": {"elo_diff": elo_diff},
    }


def test_slate_rankings_keep_distinct_champions() -> None:
    records = [
        _record(
            record_id="a",
            event_id="a",
            home="Strong",
            away="Weak",
            model=(0.62, 0.22, 0.16),
            market=(0.60, 0.23, 0.17),
            odds=(1.75, 4.40, 6.50),
            elo_diff=140,
        ),
        _record(
            record_id="b",
            event_id="b",
            home="Balanced A",
            away="Balanced B",
            model=(0.35, 0.34, 0.31),
            market=(0.39, 0.28, 0.33),
            odds=(2.70, 3.60, 3.10),
            elo_diff=8,
        ),
        _record(
            record_id="c",
            event_id="c",
            home="Favourite",
            away="Outsider",
            model=(0.48, 0.29, 0.23),
            market=(0.54, 0.27, 0.19),
            odds=(1.95, 3.90, 5.80),
            elo_diff=70,
        ),
    ]

    report = build_slate_rankings(records)
    rankings = report["rankings"]

    assert report["decision_weight"] == 0.0
    assert rankings["strongest_result_call"]["event_id"] == "a"
    assert rankings["highest_draw_probability"]["event_id"] == "b"
    assert rankings["highest_draw_uplift_vs_market"]["event_id"] == "b"
    assert rankings["most_balanced_match"]["event_id"] == "b"
    assert rankings["strongest_outsider_non_loss"]["event_id"] in {"b", "c"}
    assert rankings["best_price_discrepancy"]["event_id"] in {"b", "c"}


def test_latest_record_per_event_is_used() -> None:
    old = _record(
        record_id="old",
        event_id="same",
        home="A",
        away="B",
        model=(0.55, 0.25, 0.20),
        market=(0.52, 0.27, 0.21),
        odds=(1.90, 4.10, 5.00),
        elo_diff=50,
        retrieved="2026-09-04T08:00:00Z",
    )
    new = _record(
        record_id="new",
        event_id="same",
        home="A",
        away="B",
        model=(0.40, 0.34, 0.26),
        market=(0.43, 0.30, 0.27),
        odds=(2.40, 3.50, 4.00),
        elo_diff=10,
        retrieved="2026-09-04T10:00:00Z",
    )

    report = build_slate_rankings([old, new])
    assert report["fixture_count"] == 1
    assert report["rankings"]["highest_draw_probability"]["source_record_id"] == "new"


def test_empty_slate_is_explicit() -> None:
    report = build_slate_rankings([])
    assert report["fixture_count"] == 0
    assert report["rankings"] == {}
