from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football1.live_odds import API_BASE, DEFAULT_ODDS_FORMAT, DEFAULT_REGIONS, SPORT_KEY, _safe_error_body


MARKET_KEY = "double_chance"


def _usage(headers: Any) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for key, header in (
        ("requests_remaining", "x-requests-remaining"),
        ("requests_used", "x-requests-used"),
        ("requests_last", "x-requests-last"),
    ):
        value = headers.get(header)
        try:
            result[key] = int(value) if value is not None else None
        except ValueError:
            result[key] = None
    return result


def fetch_event_double_chance(
    api_key: str,
    event_id: str,
    *,
    regions: str = DEFAULT_REGIONS,
    odds_format: str = DEFAULT_ODDS_FORMAT,
    timeout: int = 30,
) -> tuple[dict[str, Any], dict[str, int | None]]:
    """Fetch the optional event-level double-chance market for one EPL fixture."""
    if not api_key.strip():
        raise ValueError("API key is empty")
    if not event_id.strip():
        raise ValueError("event_id is empty")

    query = urllib.parse.urlencode(
        {
            "apiKey": api_key,
            "regions": regions,
            "markets": MARKET_KEY,
            "oddsFormat": odds_format,
            "dateFormat": "iso",
        }
    )
    url = f"{API_BASE}/sports/{SPORT_KEY}/events/{urllib.parse.quote(event_id)}/odds?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Football1Research/0.1"})

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
    if not isinstance(payload, dict):
        raise ValueError("Expected event-odds response to be a JSON object")
    return payload, _usage(headers)


def summarize_double_chance_event(event: dict[str, Any]) -> dict[str, Any]:
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    if not home or not away:
        raise ValueError("Event is missing home_team or away_team")

    names = {
        "1X": f"{home} or Draw",
        "X2": f"{away} or Draw",
        "12": f"{home} or {away}",
    }
    best: dict[str, float | None] = {"1X": None, "X2": None, "12": None}
    complete_bookmakers: list[str] = []
    bookmaker_prices: list[dict[str, Any]] = []

    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market.get("key") != MARKET_KEY:
                continue
            by_name: dict[str, float] = {}
            for outcome in market.get("outcomes", []):
                name = str(outcome.get("name") or "")
                try:
                    price = float(outcome.get("price"))
                except (TypeError, ValueError):
                    continue
                if price > 1.0:
                    by_name[name] = price
            try:
                prices = {label: by_name[name] for label, name in names.items()}
            except KeyError:
                continue
            title = str(bookmaker.get("title") or bookmaker.get("key") or "unknown")
            complete_bookmakers.append(title)
            bookmaker_prices.append({"bookmaker": title, "prices": prices})
            for label, price in prices.items():
                current = best[label]
                best[label] = price if current is None else max(current, price)
            break

    return {
        "event_id": event.get("id"),
        "commence_time": event.get("commence_time"),
        "home_team": home,
        "away_team": away,
        "market": MARKET_KEY,
        "complete_bookmaker_count": len(complete_bookmakers),
        "complete_bookmakers": complete_bookmakers,
        "best_decimal_odds": best,
        "bookmaker_prices": bookmaker_prices,
    }


def select_events_from_h2h_snapshot(
    snapshot: dict[str, Any],
    *,
    event_ids: list[str] | None = None,
    max_events: int = 0,
) -> list[dict[str, Any]]:
    summaries = [item for item in snapshot.get("summary", []) if item.get("event_id")]
    if event_ids:
        wanted = set(event_ids)
        return [item for item in summaries if str(item["event_id"]) in wanted]
    if max_events <= 0:
        return []
    return summaries[:max_events]


def build_double_chance_snapshot(
    *,
    source_h2h_snapshot: dict[str, Any],
    event_results: list[tuple[dict[str, Any], dict[str, int | None]]],
    regions: str,
    odds_format: str,
    retrieved_at_utc: str | None = None,
) -> dict[str, Any]:
    summaries = [summarize_double_chance_event(payload) for payload, _ in event_results]
    usage = [item for _, item in event_results]
    region_count = len([part for part in regions.split(",") if part.strip()])
    return {
        "provider": "the-odds-api",
        "sport_key": SPORT_KEY,
        "market": MARKET_KEY,
        "retrieved_at_utc": retrieved_at_utc or datetime.now(timezone.utc).isoformat(),
        "source_h2h_retrieved_at_utc": source_h2h_snapshot.get("retrieved_at_utc"),
        "request": {
            "regions": regions,
            "odds_format": odds_format,
            "event_level_market": True,
        },
        "event_count": len(summaries),
        "estimated_max_usage_credits": len(summaries) * region_count,
        "usage_by_event": usage,
        "summary": summaries,
        "warning": (
            "Double-chance is an optional event-level market. It is intentionally not fetched by the default "
            "EPL 1X2 snapshot workflow because each selected event can consume additional API quota."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Optionally fetch EPL double-chance odds for explicitly selected events."
    )
    parser.add_argument(
        "--h2h-snapshot",
        type=Path,
        default=Path("data/live/epl_odds_snapshot.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/live/epl_double_chance_snapshot.json"),
    )
    parser.add_argument("--event-id", action="append", default=[])
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Explicitly allow the first N snapshot events to consume event-level market credits.",
    )
    parser.add_argument("--regions", default=DEFAULT_REGIONS)
    parser.add_argument("--odds-format", default=DEFAULT_ODDS_FORMAT)
    parser.add_argument("--timeout", type=int, default=30)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    api_key = os.environ.get("THE_ODDS_API_KEY", "")
    if not api_key:
        raise SystemExit("THE_ODDS_API_KEY is not set")
    source = json.loads(args.h2h_snapshot.read_text(encoding="utf-8"))
    selected = select_events_from_h2h_snapshot(
        source,
        event_ids=args.event_id or None,
        max_events=args.max_events,
    )
    if not selected:
        raise SystemExit(
            "No double-chance events selected. Pass --event-id EVENT_ID (repeatable) or --max-events N. "
            "This explicit opt-in prevents accidental API-credit use."
        )

    region_count = len([part for part in args.regions.split(",") if part.strip()])
    print(
        f"selected_events={len(selected)} estimated_max_usage_credits={len(selected) * region_count} "
        f"market={MARKET_KEY}"
    )
    results: list[tuple[dict[str, Any], dict[str, int | None]]] = []
    for item in selected:
        payload, usage = fetch_event_double_chance(
            api_key,
            str(item["event_id"]),
            regions=args.regions,
            odds_format=args.odds_format,
            timeout=args.timeout,
        )
        results.append((payload, usage))

    snapshot = build_double_chance_snapshot(
        source_h2h_snapshot=source,
        event_results=results,
        regions=args.regions,
        odds_format=args.odds_format,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote optional double-chance snapshot to {args.output}")
    for summary in snapshot["summary"]:
        print(
            summary["commence_time"],
            f"{summary['home_team']} vs {summary['away_team']}",
            f"books={summary['complete_bookmaker_count']}",
            f"best={summary['best_decimal_odds']}",
        )


if __name__ == "__main__":
    main()
