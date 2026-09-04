from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football1.live_odds import _complete_h2h, _devig


SCHEMA_VERSION = 1


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"Timestamp must include timezone: {value}")
    return dt.astimezone(timezone.utc)


def odds_record_hash(record_without_hash: dict[str, Any]) -> str:
    encoded = json.dumps(record_without_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bookmaker_quote(
    bookmaker: dict[str, Any],
    *,
    home_team: str,
    away_team: str,
) -> dict[str, Any] | None:
    prices = _complete_h2h(bookmaker, home_team, away_team)
    if prices is None:
        return None
    fair = _devig(prices)
    implied = tuple(1.0 / price for price in prices)
    key = str(bookmaker.get("key") or "")
    title = str(bookmaker.get("title") or key or "unknown")
    return {
        "bookmaker_key": key,
        "bookmaker_title": title,
        "last_update_utc": bookmaker.get("last_update"),
        "decimal_odds": {"home": prices[0], "draw": prices[1], "away": prices[2]},
        "fair_probability": {"home": fair[0], "draw": fair[1], "away": fair[2]},
        "overround": sum(implied),
    }


def _dispersion(quotes: list[dict[str, Any]]) -> dict[str, float | None]:
    if len(quotes) < 2:
        return {"home": None, "draw": None, "away": None}
    return {
        label: statistics.pstdev(float(q["fair_probability"][label]) for q in quotes)
        for label in ("home", "draw", "away")
    }


def normalize_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert one raw Odds API response into compact, hash-verified event snapshots.

    Only complete H/D/A bookmaker quotes for events still in the future at the
    retrieval timestamp are retained. The API key is never present in the raw
    snapshot and therefore can never enter this archive.
    """
    retrieved_at = str(snapshot["retrieved_at_utc"])
    retrieved = _parse_utc(retrieved_at)
    request = snapshot.get("request") or {}
    records: list[dict[str, Any]] = []

    for event in snapshot.get("events", []):
        event_id = str(event.get("id") or "")
        commence_time = str(event.get("commence_time") or "")
        if not event_id or not commence_time:
            continue
        kickoff = _parse_utc(commence_time)
        if kickoff <= retrieved:
            continue

        home = str(event.get("home_team") or "")
        away = str(event.get("away_team") or "")
        if not home or not away:
            continue

        quotes = [
            quote
            for bookmaker in event.get("bookmakers", [])
            if (quote := _bookmaker_quote(bookmaker, home_team=home, away_team=away)) is not None
        ]
        quotes.sort(key=lambda q: (str(q["bookmaker_key"]), str(q["bookmaker_title"])))
        if not quotes:
            continue

        consensus = {
            label: statistics.fmean(float(q["fair_probability"][label]) for q in quotes)
            for label in ("home", "draw", "away")
        }
        best = {
            label: max(float(q["decimal_odds"][label]) for q in quotes)
            for label in ("home", "draw", "away")
        }
        record_id = hashlib.sha256(f"{event_id}|{retrieved_at}".encode("utf-8")).hexdigest()[:24]
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "record_id": record_id,
            "status": "pre_kickoff_odds_snapshot",
            "provider": str(snapshot.get("provider") or "the-odds-api"),
            "sport_key": str(snapshot.get("sport_key") or "soccer_epl"),
            "retrieved_at_utc": retrieved_at,
            "event_id": event_id,
            "commence_time_utc": commence_time,
            "home_team": home,
            "away_team": away,
            "request": {
                "regions": request.get("regions"),
                "markets": request.get("markets"),
                "odds_format": request.get("odds_format"),
            },
            "complete_h2h_bookmaker_count": len(quotes),
            "consensus_fair_probability": consensus,
            "fair_probability_dispersion": _dispersion(quotes),
            "best_decimal_odds": best,
            "mean_bookmaker_overround": statistics.fmean(float(q["overround"]) for q in quotes),
            "bookmakers": quotes,
        }
        record["content_sha256"] = odds_record_hash(record)
        records.append(record)

    records.sort(key=lambda row: (row["commence_time_utc"], row["event_id"]))
    return records


def append_odds_records(path: Path, records: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if path.exists():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            record_id = str(row.get("record_id") or "")
            if not record_id:
                raise ValueError(f"Odds archive line {line_number} has no record_id")
            stored = row.get("content_sha256")
            unsigned = dict(row)
            unsigned.pop("content_sha256", None)
            if stored != odds_record_hash(unsigned):
                raise ValueError(f"Odds archive line {line_number} failed content hash verification")
            existing_ids.add(record_id)

    new_records = [record for record in records if record["record_id"] not in existing_ids]
    if not new_records:
        return 0
    with path.open("a", encoding="utf-8") as handle:
        for record in new_records:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return len(new_records)


def archive_snapshot(snapshot_path: Path, archive_path: Path) -> dict[str, Any]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    records = normalize_snapshot(snapshot)
    appended = append_odds_records(archive_path, records)
    return {
        "snapshot_retrieved_at_utc": snapshot["retrieved_at_utc"],
        "normalized_event_snapshots": len(records),
        "appended_event_snapshots": appended,
        "archive": str(archive_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append a normalized pre-kickoff EPL odds snapshot to the durable quote archive."
    )
    parser.add_argument("--snapshot", type=Path, default=Path("data/live/epl_odds_snapshot.json"))
    parser.add_argument("--archive", type=Path, default=Path("prospective/odds_snapshots.jsonl"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = archive_snapshot(args.snapshot, args.archive)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
