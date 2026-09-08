from football1.live_odds import build_snapshot, summarize_event


def sample_event():
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
                "last_update": "2026-09-08T00:00:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-09-08T00:01:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.0},
                            {"name": "Draw", "price": 3.5},
                            {"name": "Liverpool", "price": 4.0},
                        ],
                    }
                ],
            },
            {
                "key": "book_b",
                "title": "Book B",
                "last_update": "2026-09-08T00:02:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-09-08T00:03:00Z",
                        "outcomes": [
                            {"name": "Liverpool", "price": 3.8},
                            {"name": "Arsenal", "price": 2.1},
                            {"name": "Draw", "price": 3.6},
                        ],
                    }
                ],
            },
        ],
    }


def test_event_summary_uses_best_prices_and_devigged_consensus():
    summary = summarize_event(sample_event())
    assert summary["complete_h2h_bookmaker_count"] == 2
    assert summary["best_decimal_odds"] == {"home": 2.1, "draw": 3.6, "away": 4.0}
    assert summary["best_price_quotes"]["home"] == {
        "decimal_odds": 2.1,
        "bookmaker_key": "book_b",
        "bookmaker_title": "Book B",
        "bookmaker_last_update": "2026-09-08T00:02:00Z",
        "market_last_update": "2026-09-08T00:03:00Z",
    }
    assert summary["best_price_quotes"]["away"]["bookmaker_title"] == "Book A"
    assert [q["bookmaker_title"] for q in summary["quote_board"]["home"]] == ["Book B", "Book A"]
    consensus = summary["consensus_fair_probability"]
    assert consensus is not None
    assert abs(sum(consensus.values()) - 1.0) < 1e-12


def test_snapshot_never_contains_api_key_parameter_and_uses_gbp():
    snapshot = build_snapshot(
        [sample_event()],
        {"requests_last": 1, "requests_used": 1, "requests_remaining": 499},
        retrieved_at_utc="2026-09-04T09:00:00+00:00",
    )
    assert "apiKey" not in snapshot["request"]
    assert snapshot["event_count"] == 1
    assert snapshot["usage"]["requests_remaining"] == 499
    assert snapshot["competition"] == "English Premier League"
    assert snapshot["portfolio_currency"] == "GBP"


def test_incomplete_bookmaker_is_excluded_from_consensus_and_best_price_board():
    event = sample_event()
    event["bookmakers"].append(
        {
            "key": "broken",
            "title": "Broken Book",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Arsenal", "price": 2.2},
                        {"name": "Liverpool", "price": 3.5},
                    ],
                }
            ],
        }
    )
    summary = summarize_event(event)
    assert summary["bookmaker_count"] == 3
    assert summary["complete_h2h_bookmaker_count"] == 2
    assert "Broken Book" not in summary["complete_h2h_bookmakers"]
    assert all(q["bookmaker_title"] != "Broken Book" for q in summary["quote_board"]["home"])
