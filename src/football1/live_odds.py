from __future__ import annotations

import argparse
import json
import os
import statistics
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "soccer_epl"
DEFAULT_REGIONS = "uk"
DEFAULT_MARKETS = "h2h"
DEFAULT_ODDS_FORMAT = "decimal"


def _devig(prices: tuple[float, float, float]) -> tuple[float, float, float]:
    implied = [1.0 / p for p in prices]
    total = sum(implied)
    return tuple(x / total for x in implied)  # type: ignore[return-value]


def _safe_error_body(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")[:500]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text.strip()
    if isinstance(payload, dict):
        code = payload.get("error_code") or payload.get("code")
        message = payload.get("message") or payload.get("error")
        parts = [str(x) for x in (code, message) if x]
        return ": ".join(parts) if parts else "API error"
    return "API error"


def fetch_epl_odds(
    api_key: str,
    *,
    regions: str = DEFAULT_REGIONS,
    markets: str = DEFAULT_MARKETS,
    odds_format: str = DEFAULT_ODDS_FORMAT,
    timeout: int = 30,
) -> tuple[list[dict[str, Any]], dict[str, int | None]]:
    """Fetch current/upcoming EPL odds without logging or returning the API key."""
    if not api_key.strip():
        raise ValueError("API key is empty")

    query = urllib.parse.urlencode(
        {
            "apiKey": api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": "iso",
        }
    )
    url = f"{API_BASE}/sports/{SPORT_KEY}/odds?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Football1Research/0.1"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            headers = response.headers
    except urllib.error.HTTPError as exc:
        body = _safe_error_body(exc.read())
        raise RuntimeError(f"The Odds API returned HTTP {exc.code}: {body}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"The Odds API network request failed: {exc.reason}") from None

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The Odds API returned invalid JSON") from exc

    if not isinstance(payload, list):
        raise ValueError("Expected The Odds API EPL response to be a list of events")

    usage: dict[str, int | None] = {}
    for key, header in (
        ("requests_remaining", "x-requests-remaining"),
        ("requests_used", "x-requests-used"),
        ("requests_last", "x-requests-last"),
    ):
        value = headers.get(header)
        try:
            usage[key] = int(value) if value is not None else None
        except ValueError:
            usage[key] = None

    return payload, usage


def _complete_h2h(
    bookmaker: dict[str, Any],
    home_team: str,
    away_team: str,
) -> tuple[float, float, float] | None:
    for market in bookmaker.get("markets", []):
        if market.get("key") != "h2h":
            continue
        outcomes = {
            str(item.get("name")): item.get("price")
            for item in market.get("outcomes", [])
        }
        try:
            prices = (
                float(outcomes[home_team]),
                float(outcomes["Draw"]),
                float(outcomes[away_team]),
            )
        except (KeyError, TypeError, ValueError):
            return None
        if any(price <= 1.0 for price in prices):
            return None
        return prices
    return None


def summarize_event(event: dict[str, Any]) -> dict[str, Any]:
    home = str(event.get("home_team", ""))
    away = str(event.get("away_team", ""))
    if not home or not away:
        raise ValueError("Event is missing home_team or away_team")

    fair_rows: list[tuple[float, float, float]] = []
    complete_bookmakers: list[str] = []
    best = {"home": None, "draw": None, "away": None}

    for bookmaker in event.get("bookmakers", []):
        prices = _complete_h2h(bookmaker, home, away)
        if prices is None:
            continue
        complete_bookmakers.append(str(bookmaker.get("title") or bookmaker.get("key") or "unknown"))
        fair_rows.append(_devig(prices))
        for label, price in zip(("home", "draw", "away"), prices):
            current = best[label]
            best[label] = price if current is None else max(float(current), price)

    consensus = None
    if fair_rows:
        consensus = {
            "home": statistics.fmean(row[0] for row in fair_rows),
            "draw": statistics.fmean(row[1] for row in fair_rows),
            "away": statistics.fmean(row[2] for row in fair_rows),
        }

    return {
        "event_id": event.get("id"),
        "commence_time": event.get("commence_time"),
        "home_team": home,
        "away_team": away,
        "bookmaker_count": len(event.get("bookmakers", [])),
        "complete_h2h_bookmaker_count": len(fair_rows),
        "complete_h2h_bookmakers": complete_bookmakers,
        "consensus_fair_probability": consensus,
        "best_decimal_odds": best,
    }


def build_snapshot(
    events: list[dict[str, Any]],
    usage: dict[str, int | None],
    *,
    regions: str = DEFAULT_REGIONS,
    markets: str = DEFAULT_MARKETS,
    odds_format: str = DEFAULT_ODDS_FORMAT,
    retrieved_at_utc: str | None = None,
) -> dict[str, Any]:
    retrieved = retrieved_at_utc or datetime.now(timezone.utc).isoformat()
    summaries = [summarize_event(event) for event in events]
    return {
        "provider": "the-odds-api",
        "sport_key": SPORT_KEY,
        "retrieved_at_utc": retrieved,
        "request": {
            "regions": regions,
            "markets": markets,
            "odds_format": odds_format,
        },
        "usage": usage,
        "event_count": len(events),
        "events": events,
        "summary": summaries,
    }


def write_snapshot(snapshot: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch one current EPL 1X2 odds snapshot from The Odds API."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/live/epl_odds_snapshot.json"),
    )
    parser.add_argument("--regions", default=DEFAULT_REGIONS)
    parser.add_argument("--markets", default=DEFAULT_MARKETS)
    parser.add_argument("--odds-format", default=DEFAULT_ODDS_FORMAT)
    parser.add_argument("--timeout", type=int, default=30)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    api_key = os.environ.get("THE_ODDS_API_KEY", "")
    if not api_key:
        raise SystemExit("THE_ODDS_API_KEY is not set")

    events, usage = fetch_epl_odds(
        api_key,
        regions=args.regions,
        markets=args.markets,
        odds_format=args.odds_format,
        timeout=args.timeout,
    )
    snapshot = build_snapshot(
        events,
        usage,
        regions=args.regions,
        markets=args.markets,
        odds_format=args.odds_format,
    )
    write_snapshot(snapshot, args.output)

    print(f"wrote live EPL odds snapshot to {args.output}")
    print(f"events={snapshot['event_count']}")
    print(
        "usage_last=", usage.get("requests_last"),
        "usage_used=", usage.get("requests_used"),
        "usage_remaining=", usage.get("requests_remaining"),
    )
    for item in snapshot["summary"]:
        consensus = item["consensus_fair_probability"]
        best = item["best_decimal_odds"]
        print(
            item["commence_time"],
            f"{item['home_team']} vs {item['away_team']}",
            f"books={item['complete_h2h_bookmaker_count']}",
            f"consensus={consensus}",
            f"best={best}",
        )


if __name__ == "__main__":
    main()
