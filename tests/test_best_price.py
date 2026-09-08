import pytest

from football1.best_price import best_price_for_outcome, best_price_quotes


def _summary():
    return {
        "complete_h2h_bookmaker_count": 3,
        "best_price_quotes": {
            "home": {
                "decimal_odds": 2.2,
                "bookmaker_key": "book_a",
                "bookmaker_title": "Book A",
                "bookmaker_last_update": "2026-09-08T00:00:00Z",
                "market_last_update": "2026-09-08T00:01:00Z",
            },
            "draw": None,
            "away": {
                "decimal_odds": 3.4,
                "bookmaker_key": "book_b",
                "bookmaker_title": "Book B",
                "bookmaker_last_update": None,
                "market_last_update": None,
            },
        },
    }


def test_best_price_quote_keeps_bookmaker_provenance_and_universe_size():
    quote = best_price_for_outcome(_summary(), "home")
    assert quote == {
        "outcome": "home",
        "decimal_odds": 2.2,
        "bookmaker_key": "book_a",
        "bookmaker_title": "Book A",
        "bookmaker_last_update": "2026-09-08T00:00:00Z",
        "market_last_update": "2026-09-08T00:01:00Z",
        "complete_bookmaker_count": 3,
    }


def test_missing_outcome_quote_remains_none():
    assert best_price_quotes(_summary())["draw"] is None


def test_unknown_outcome_is_rejected():
    with pytest.raises(ValueError):
        best_price_for_outcome(_summary(), "double_chance")
