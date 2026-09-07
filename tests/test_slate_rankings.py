from __future__ import annotations

from datetime import datetime, timezone

from football1.slate_rankings import build_slate_rankings


AS_OF = datetime(2026, 9, 7, 20, 0, tzinfo=timezone.utc)


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
    commence: str = "2026-09-10T14:00:00Z",
) -> dict:
    return {
        "record_id": record_id,
        "event_id": event_id,
        "status": "prediction_locked",
        "commence_time_utc": commence,
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

    report = build_slate_rankings(records, now_utc=AS_OF)
    rankings = report["rankings"]

    assert report["schema_version"] == 3
    assert report["decision_weight"] == 0.0
    assert report["scope"] == "future_locked_latest_per_event"
    assert report["fixture_count"] == 3
    assert rankings["strongest_result_call"]["event_id"] == "a"
    assert rankings["highest_draw_probability"]["event_id"] == "b"
    assert rankings["highest_draw_uplift_vs_market"]["event_id"] == "b"
    assert rankings["most_balanced_match"]["event_id"] == "b"
    assert rankings["strongest_outsider_non_loss"]["event_id"] in {"b", "c"}
    assert rankings["best_price_discrepancy"]["event_id"] in {"b", "c"}
    assert rankings["strongest_model_disagreement"]["selected_hda_price_detail"] is not None
    assert rankings["strongest_quote_premium"]["selected_hda_price_detail"] is not None
    assert rankings["strongest_total_probability_edge"]["selected_hda_price_detail"] is not None


def test_raw_long_odds_ev_is_not_confused_with_model_disagreement() -> None:
    longshot = _record(
        record_id="long",
        event_id="long",
        home="Huge Favourite",
        away="Longshot",
        model=(0.80, 0.13, 0.07),
        market=(0.81, 0.125, 0.065),
        odds=(1.18, 8.5, 18.0),
        elo_diff=250,
    )
    conviction = _record(
        record_id="conviction",
        event_id="conviction",
        home="Model Lean",
        away="Peer",
        model=(0.45, 0.30, 0.25),
        market=(0.40, 0.30, 0.30),
        odds=(2.40, 3.40, 3.50),
        elo_diff=20,
    )

    report = build_slate_rankings([longshot, conviction], now_utc=AS_OF)
    rankings = report["rankings"]

    assert rankings["best_price_discrepancy"]["event_id"] == "long"
    assert rankings["best_price_discrepancy"]["outcome"] == "away"
    assert rankings["strongest_model_disagreement"]["event_id"] == "conviction"
    assert rankings["strongest_model_disagreement"]["outcome"] == "home"
    assert rankings["strongest_model_disagreement"]["ranking_score"] == 0.05


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

    report = build_slate_rankings([old, new], now_utc=AS_OF)
    assert report["fixture_count"] == 1
    assert report["rankings"]["highest_draw_probability"]["source_record_id"] == "new"


def test_future_only_default_excludes_started_fixtures() -> None:
    past = _record(
        record_id="past",
        event_id="past",
        home="Past A",
        away="Past B",
        model=(0.80, 0.10, 0.10),
        market=(0.70, 0.15, 0.15),
        odds=(1.50, 8.0, 8.0),
        elo_diff=200,
        commence="2026-09-05T14:00:00Z",
    )
    future = _record(
        record_id="future",
        event_id="future",
        home="Future A",
        away="Future B",
        model=(0.40, 0.32, 0.28),
        market=(0.41, 0.30, 0.29),
        odds=(2.50, 3.50, 3.70),
        elo_diff=12,
        commence="2026-09-12T14:00:00Z",
    )

    report = build_slate_rankings([past, future], now_utc=AS_OF)
    assert report["latest_locked_event_count"] == 2
    assert report["excluded_started_event_count"] == 1
    assert report["fixture_count"] == 1
    assert report["rankings"]["strongest_result_call"]["event_id"] == "future"

    historical = build_slate_rankings([past, future], now_utc=AS_OF, include_started=True)
    assert historical["scope"] == "all_locked_latest_per_event"
    assert historical["fixture_count"] == 2
    assert historical["excluded_started_event_count"] == 0


def test_empty_slate_is_explicit() -> None:
    report = build_slate_rankings([], now_utc=AS_OF)
    assert report["fixture_count"] == 0
    assert report["rankings"] == {}
