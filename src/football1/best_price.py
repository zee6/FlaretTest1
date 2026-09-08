from __future__ import annotations

from typing import Any, Mapping

OUTCOMES = ("home", "draw", "away")


def best_price_quotes(summary: Mapping[str, Any]) -> dict[str, dict[str, Any] | None]:
    """Return UI-ready best-price quotes from a live-odds event summary.

    This module is intentionally commercial-neutral. It only reads analytical
    quote provenance already present in the event summary.
    """
    raw = summary.get("best_price_quotes")
    if not isinstance(raw, Mapping):
        return {outcome: None for outcome in OUTCOMES}

    result: dict[str, dict[str, Any] | None] = {}
    for outcome in OUTCOMES:
        quote = raw.get(outcome)
        if not isinstance(quote, Mapping):
            result[outcome] = None
            continue
        result[outcome] = {
            "outcome": outcome,
            "decimal_odds": float(quote["decimal_odds"]),
            "bookmaker_key": quote.get("bookmaker_key"),
            "bookmaker_title": quote.get("bookmaker_title"),
            "bookmaker_last_update": quote.get("bookmaker_last_update"),
            "market_last_update": quote.get("market_last_update"),
            "complete_bookmaker_count": int(summary.get("complete_h2h_bookmaker_count", 0)),
        }
    return result


def best_price_for_outcome(summary: Mapping[str, Any], outcome: str) -> dict[str, Any] | None:
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    return best_price_quotes(summary)[outcome]
