from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football1.features import (
    FeatureRow,
    TeamState,
    _rest_days,
    _summarize,
    _update_state,
    build_feature_rows,
)
from football1.offset_slant import fit_offset_slant


MODEL_ID = "fixed_market_offset_football_slant_v1_live_consensus_anchor"
MODEL_ALPHA = 0.10

# The Odds API names -> Football-Data canonical names.
TEAM_ALIASES = {
    "Brighton and Hove Albion": "Brighton",
    "Coventry City": "Coventry",
    "Hull City": "Hull",
    "Ipswich Town": "Ipswich",
    "Leeds United": "Leeds",
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Tottenham Hotspur": "Tottenham",
}


def canonical_team_name(provider_name: str) -> str:
    return TEAM_ALIASES.get(provider_name, provider_name)


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"Timestamp must include timezone: {value}")
    return dt.astimezone(timezone.utc)


def _season_start_year(dt: datetime) -> int:
    return dt.year if dt.month >= 7 else dt.year - 1


def _historical_records_before(db_path: Path, cutoff_date: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT match_id, season_start_year, match_date, kickoff_time,
                   home_team, away_team, fthg, ftag, ftr, raw_json
            FROM matches
            WHERE match_date < ?
            ORDER BY match_date, match_id
            """,
            (cutoff_date,),
        ).fetchall()
    finally:
        conn.close()


def _states_as_of(db_path: Path, cutoff_date: str) -> tuple[dict[str, TeamState], str | None]:
    states: dict[str, TeamState] = defaultdict(TeamState)
    records = _historical_records_before(db_path, cutoff_date)
    for record in records:
        _update_state(record, states)
    latest = records[-1]["match_date"] if records else None
    return states, latest


def _live_feature_row(
    *,
    event_id: str,
    commence_time: str,
    home_team: str,
    away_team: str,
    states: dict[str, TeamState],
) -> FeatureRow:
    kickoff = _parse_utc(commence_time)
    match_date = kickoff.date().isoformat()
    home_name = canonical_team_name(home_team)
    away_name = canonical_team_name(away_team)
    if home_name not in states or states[home_name].total_games == 0:
        raise ValueError(f"No historical team state for live home team {home_team!r} -> {home_name!r}")
    if away_name not in states or states[away_name].total_games == 0:
        raise ValueError(f"No historical team state for live away team {away_team!r} -> {away_name!r}")

    home = states[home_name]
    away = states[away_name]
    h5, a5 = _summarize(home, 5), _summarize(away, 5)
    h10, a10 = _summarize(home, 10), _summarize(away, 10)
    return FeatureRow(
        match_id=event_id,
        season_start_year=_season_start_year(kickoff),
        match_date=match_date,
        home_team=home_name,
        away_team=away_name,
        result="",
        elo_diff=home.elo - away.elo,
        ppg5_diff=h5["ppg"] - a5["ppg"],
        gf5_diff=h5["gf"] - a5["gf"],
        ga5_diff=h5["ga"] - a5["ga"],
        shots5_diff=h5["shots_for"] - a5["shots_for"],
        shots_allowed5_diff=h5["shots_against"] - a5["shots_against"],
        sot5_diff=h5["sot_for"] - a5["sot_for"],
        sot_allowed5_diff=h5["sot_against"] - a5["sot_against"],
        ppg10_diff=h10["ppg"] - a10["ppg"],
        gf10_diff=h10["gf"] - a10["gf"],
        ga10_diff=h10["ga"] - a10["ga"],
        rest_days_diff=_rest_days(home, match_date) - _rest_days(away, match_date),
        log_prior_games_home=math.log1p(home.total_games),
        log_prior_games_away=math.log1p(away.total_games),
        b365_home=None,
        b365_draw=None,
        b365_away=None,
    )


def _probability_tuple(raw: dict[str, Any]) -> tuple[float, float, float]:
    values = (float(raw["home"]), float(raw["draw"]), float(raw["away"]))
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("Market consensus probabilities must be positive and finite")
    if abs(sum(values) - 1.0) > 1e-6:
        raise ValueError("Market consensus probabilities must sum to 1")
    return values


def _odds_tuple(raw: dict[str, Any]) -> tuple[float, float, float]:
    values = (float(raw["home"]), float(raw["draw"]), float(raw["away"]))
    if any(not math.isfinite(v) or v <= 1.0 for v in values):
        raise ValueError("Best decimal odds must contain three finite prices > 1")
    return values


def prediction_content_hash(record_without_hash: dict[str, Any]) -> str:
    encoded = json.dumps(record_without_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _prediction_lock_key(record: dict[str, Any]) -> tuple[str, str]:
    event_id = str(record.get("event_id") or "")
    model = record.get("model")
    model_id = str(model.get("id") or "") if isinstance(model, dict) else ""
    if not event_id or not model_id:
        raise ValueError("Prediction record must contain event_id and model.id")
    return event_id, model_id


def make_prediction_record(
    *,
    event: dict[str, Any],
    snapshot_retrieved_at_utc: str,
    model_probability: tuple[float, float, float],
    feature_row: FeatureRow,
    training_matches: int,
    historical_data_cutoff: str | None,
    alpha: float = MODEL_ALPHA,
) -> dict[str, Any]:
    retrieved = _parse_utc(snapshot_retrieved_at_utc)
    kickoff = _parse_utc(str(event["commence_time"]))
    if kickoff <= retrieved:
        raise ValueError("Prospective prediction must be recorded before kickoff")

    market_probability = _probability_tuple(event["consensus_fair_probability"])
    best_odds = _odds_tuple(event["best_decimal_odds"])
    if abs(sum(model_probability) - 1.0) > 1e-6 or any(p <= 0 for p in model_probability):
        raise ValueError("Model probabilities must be positive and sum to 1")

    labels = ("home", "draw", "away")
    model_dict = dict(zip(labels, model_probability))
    market_dict = dict(zip(labels, market_probability))
    best_dict = dict(zip(labels, best_odds))
    residual = {label: model_dict[label] - market_dict[label] for label in labels}
    predicted_ev = {label: model_dict[label] * best_dict[label] - 1.0 for label in labels}
    max_ev_outcome = max(labels, key=lambda label: predicted_ev[label])

    identity_seed = "|".join(
        [
            str(event["event_id"]),
            snapshot_retrieved_at_utc,
            MODEL_ID,
        ]
    ).encode("utf-8")
    record_id = hashlib.sha256(identity_seed).hexdigest()[:24]

    record: dict[str, Any] = {
        "schema_version": 1,
        "record_id": record_id,
        "status": "prediction_locked",
        "provider": "the-odds-api",
        "sport_key": "soccer_epl",
        "event_id": event["event_id"],
        "commence_time_utc": event["commence_time"],
        "snapshot_retrieved_at_utc": snapshot_retrieved_at_utc,
        "home_team_provider": event["home_team"],
        "away_team_provider": event["away_team"],
        "home_team_canonical": feature_row.home_team,
        "away_team_canonical": feature_row.away_team,
        "complete_h2h_bookmaker_count": event["complete_h2h_bookmaker_count"],
        "market_anchor": {
            "type": "mean_of_individually_devigged_complete_uk_h2h_books",
            "probability": market_dict,
            "best_decimal_odds": best_dict,
        },
        "model": {
            "id": MODEL_ID,
            "alpha": alpha,
            "training_anchor": "B365 pre-closing de-vigged historical probabilities",
            "live_anchor": "multi-book UK consensus from The Odds API",
            "anchor_change_status": "prospective_experimental_not_historically_equivalent",
            "training_matches": training_matches,
            "historical_data_cutoff": historical_data_cutoff,
            "probability": model_dict,
            "probability_residual_vs_market": residual,
            "predicted_ev_at_best_odds": predicted_ev,
            "max_predicted_ev_outcome": max_ev_outcome,
            "max_predicted_ev": predicted_ev[max_ev_outcome],
            "strategy_threshold": None,
        },
        "features": asdict(feature_row),
    }
    record["content_sha256"] = prediction_content_hash(record)
    return record


def append_prediction_records(ledger_path: Path, records: list[dict[str, Any]]) -> int:
    """Append immutable prospective locks, at most once per event and model.

    Repeated market observations belong in the odds snapshot archive. A later
    quote must not silently rewrite or duplicate the original Football 1 call.
    A genuinely different model ID may create its own separate lock.
    """
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    existing_locks: set[tuple[str, str]] = set()
    if ledger_path.exists():
        for line_number, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            record_id = str(item.get("record_id", ""))
            if not record_id:
                raise ValueError(f"Ledger line {line_number} has no record_id")
            stored_hash = item.get("content_sha256")
            unsigned = dict(item)
            unsigned.pop("content_sha256", None)
            if stored_hash != prediction_content_hash(unsigned):
                raise ValueError(f"Ledger line {line_number} failed content hash verification")
            existing_ids.add(record_id)
            existing_locks.add(_prediction_lock_key(item))

    new_records: list[dict[str, Any]] = []
    pending_locks: set[tuple[str, str]] = set()
    for record in records:
        record_id = str(record.get("record_id") or "")
        if not record_id:
            raise ValueError("New prediction record has no record_id")
        stored_hash = record.get("content_sha256")
        unsigned = dict(record)
        unsigned.pop("content_sha256", None)
        if stored_hash != prediction_content_hash(unsigned):
            raise ValueError("New prediction record failed content hash verification")
        if record_id in existing_ids:
            continue
        lock_key = _prediction_lock_key(record)
        if lock_key in existing_locks or lock_key in pending_locks:
            continue
        pending_locks.add(lock_key)
        new_records.append(record)

    if not new_records:
        return 0
    with ledger_path.open("a", encoding="utf-8") as handle:
        for record in new_records:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return len(new_records)


def build_prospective_records(
    db_path: Path,
    snapshot: dict[str, Any],
    *,
    alpha: float = MODEL_ALPHA,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    retrieved_at = str(snapshot["retrieved_at_utc"])
    retrieved_dt = _parse_utc(retrieved_at)
    cutoff_date = retrieved_dt.date().isoformat()

    feature_rows = [row for row in build_feature_rows(db_path) if row.match_date < cutoff_date]
    train_rows = [
        row
        for row in feature_rows
        if row.b365_home is not None and row.b365_draw is not None and row.b365_away is not None
    ]
    if not train_rows:
        raise ValueError("No historical rows are available to train the prospective model")
    model = fit_offset_slant(train_rows, alpha=alpha)
    states, historical_cutoff = _states_as_of(db_path, cutoff_date)

    records: list[dict[str, Any]] = []
    skipped_started = 0
    skipped_incomplete_market = 0
    for event in snapshot.get("summary", []):
        kickoff = _parse_utc(str(event["commence_time"]))
        if kickoff <= retrieved_dt:
            skipped_started += 1
            continue
        if event.get("consensus_fair_probability") is None:
            skipped_incomplete_market += 1
            continue
        best = event.get("best_decimal_odds") or {}
        if any(best.get(label) is None for label in ("home", "draw", "away")):
            skipped_incomplete_market += 1
            continue

        feature_row = _live_feature_row(
            event_id=str(event["event_id"]),
            commence_time=str(event["commence_time"]),
            home_team=str(event["home_team"]),
            away_team=str(event["away_team"]),
            states=states,
        )
        base = _probability_tuple(event["consensus_fair_probability"])
        model_probability = model.predict_with_base(feature_row, base)
        records.append(
            make_prediction_record(
                event=event,
                snapshot_retrieved_at_utc=retrieved_at,
                model_probability=model_probability,
                feature_row=feature_row,
                training_matches=len(train_rows),
                historical_data_cutoff=historical_cutoff,
                alpha=alpha,
            )
        )

    records.sort(key=lambda item: (item["commence_time_utc"], item["event_id"]))
    metadata = {
        "snapshot_retrieved_at_utc": retrieved_at,
        "historical_data_cutoff": historical_cutoff,
        "training_matches": len(train_rows),
        "created_records": len(records),
        "skipped_started": skipped_started,
        "skipped_incomplete_market": skipped_incomplete_market,
        "model_id": MODEL_ID,
        "alpha": alpha,
    }
    return records, metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append pre-kickoff Football 1 predictions to the prospective ledger.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--snapshot", type=Path, default=Path("data/live/epl_odds_snapshot.json"))
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--alpha", type=float, default=MODEL_ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    records, metadata = build_prospective_records(args.database, snapshot, alpha=args.alpha)
    appended = append_prediction_records(args.ledger, records)
    print(json.dumps({**metadata, "appended_records": appended}, sort_keys=True))
    for record in records:
        m = record["model"]
        print(
            record["commence_time_utc"],
            record["home_team_provider"], "vs", record["away_team_provider"],
            "market=", record["market_anchor"]["probability"],
            "football1=", m["probability"],
            "max_ev=", round(float(m["max_predicted_ev"]), 6),
            "outcome=", m["max_predicted_ev_outcome"],
        )


if __name__ == "__main__":
    main()
