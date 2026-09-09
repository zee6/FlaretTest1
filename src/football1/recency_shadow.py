from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

from football1.features import FeatureRow, _rest_days
from football1.offset_slant import fit_offset_slant
from football1.prospective import _parse_utc, _states_as_of
from football1.recency_audit import _summarize, build_recency_feature_rows


DEFAULT_MODEL_ID = "fixed_market_offset_football_slant_v1_recency_30d_prospective_shadow"
DEFAULT_HALF_LIFE_DAYS = 30.0
DECISION_WEIGHT = 0.0
LABELS = ("home", "draw", "away")


def content_hash(record_without_hash: dict[str, Any]) -> str:
    encoded = json.dumps(record_without_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def model_id_for_half_life(half_life_days: float) -> str:
    value = float(half_life_days)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("half_life_days must be positive and finite")
    if math.isclose(value, DEFAULT_HALF_LIFE_DAYS, abs_tol=1e-12):
        return DEFAULT_MODEL_ID
    compact = f"{value:g}".replace(".", "p")
    return f"fixed_market_offset_football_slant_v1_recency_{compact}d_prospective_shadow"


def selection_provenance(half_life_days: float) -> str:
    value = float(half_life_days)
    if math.isclose(value, 30.0, abs_tol=1e-12):
        return (
            "30-day probe ranked best on inspected historical Recency Audit v1 when this shadow was first proposed; "
            "this lock is prospective confirmation only, not prior validation"
        )
    if math.isclose(value, 15.0, abs_tol=1e-12):
        return (
            "15-day probe was inspected after the 30-day result and was marginally best among the observed historical recency probes; "
            "it is post-hoc historically and this lock is prospective confirmation only, not prior validation"
        )
    return (
        f"{value:g}-day probe is an observed historical sensitivity setting; "
        "this lock is prospective confirmation only, not prior validation"
    )


def _probability_tuple(raw: dict[str, Any]) -> tuple[float, float, float]:
    values = tuple(float(raw[label]) for label in LABELS)
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("probabilities must be positive finite values")
    if abs(sum(values) - 1.0) > 1e-6:
        raise ValueError("probabilities must sum to one")
    return values  # type: ignore[return-value]


def _live_recency_feature_row(
    source: dict[str, Any],
    states: dict[str, Any],
    *,
    half_life_days: float,
) -> FeatureRow:
    kickoff = _parse_utc(str(source["commence_time_utc"]))
    match_date = kickoff.date().isoformat()
    home_name = str(source["home_team_canonical"])
    away_name = str(source["away_team_canonical"])
    if home_name not in states or states[home_name].total_games == 0:
        raise ValueError(f"No historical state for home team {home_name!r}")
    if away_name not in states or states[away_name].total_games == 0:
        raise ValueError(f"No historical state for away team {away_name!r}")
    home = states[home_name]
    away = states[away_name]
    h5 = _summarize(home, 5, current_date=match_date, half_life_days=half_life_days)
    a5 = _summarize(away, 5, current_date=match_date, half_life_days=half_life_days)
    h10 = _summarize(home, 10, current_date=match_date, half_life_days=half_life_days)
    a10 = _summarize(away, 10, current_date=match_date, half_life_days=half_life_days)
    return FeatureRow(
        match_id=str(source["event_id"]),
        season_start_year=int(source["features"]["season_start_year"]),
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


def load_source_records(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        stored = row.get("content_sha256")
        unsigned = dict(row)
        unsigned.pop("content_sha256", None)
        from football1.prospective import prediction_content_hash
        if stored != prediction_content_hash(unsigned):
            raise ValueError(f"Source ledger line {line_number} failed content hash verification")
        rows.append(row)
    return rows


def build_shadow_records(
    db_path: Path,
    source_records: list[dict[str, Any]],
    *,
    locked_at_utc: str,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    model_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    half_life = float(half_life_days)
    if not math.isfinite(half_life) or half_life <= 0:
        raise ValueError("half_life_days must be positive and finite")
    shadow_model_id = str(model_id or model_id_for_half_life(half_life))
    if not shadow_model_id:
        raise ValueError("model_id must not be empty")

    locked_at = _parse_utc(locked_at_utc)
    future = [row for row in source_records if _parse_utc(str(row["commence_time_utc"])) > locked_at]
    skipped_started = len(source_records) - len(future)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in future:
        groups.setdefault(str(row["snapshot_retrieved_at_utc"]), []).append(row)

    records: list[dict[str, Any]] = []
    for source_snapshot, rows in sorted(groups.items()):
        cutoff_date = _parse_utc(source_snapshot).date().isoformat()
        training_rows = [
            row
            for row in build_recency_feature_rows(db_path, half_life_days=half_life)
            if row.match_date < cutoff_date
            and row.b365_home is not None
            and row.b365_draw is not None
            and row.b365_away is not None
        ]
        if not training_rows:
            raise ValueError("No historical recency rows available before source snapshot")
        model = fit_offset_slant(training_rows, alpha=0.10)
        states, historical_cutoff = _states_as_of(db_path, cutoff_date)

        for source in rows:
            market = _probability_tuple(source["market_anchor"]["probability"])
            equal = _probability_tuple(source["model"]["probability"])
            feature_row = _live_recency_feature_row(
                source,
                states,
                half_life_days=half_life,
            )
            probability = model.predict_with_base(feature_row, market)
            identity = "|".join([str(source["record_id"]), shadow_model_id]).encode("utf-8")
            recency = dict(zip(LABELS, probability, strict=True))
            equal_dict = dict(zip(LABELS, equal, strict=True))
            market_dict = dict(zip(LABELS, market, strict=True))
            record: dict[str, Any] = {
                "schema_version": 1,
                "record_id": hashlib.sha256(identity).hexdigest()[:24],
                "status": "recency_shadow_locked",
                "model_id": shadow_model_id,
                "decision_weight": DECISION_WEIGHT,
                "event_id": source["event_id"],
                "commence_time_utc": source["commence_time_utc"],
                "shadow_locked_at_utc": locked_at_utc,
                "source_prediction": {
                    "record_id": source["record_id"],
                    "content_sha256": source["content_sha256"],
                    "snapshot_retrieved_at_utc": source_snapshot,
                    "model_id": source["model"]["id"],
                },
                "teams": {
                    "home": source["home_team_canonical"],
                    "away": source["away_team_canonical"],
                },
                "market_probability": market_dict,
                "equal_weight_probability": equal_dict,
                "recency_probability": recency,
                "recency_minus_equal_weight": {
                    label: recency[label] - equal_dict[label] for label in LABELS
                },
                "recency_minus_market": {
                    label: recency[label] - market_dict[label] for label in LABELS
                },
                "historical_training": {
                    "matches": len(training_rows),
                    "historical_data_cutoff": historical_cutoff,
                    "source_snapshot_cutoff_date": cutoff_date,
                    "market_training_anchor": "B365 pre-closing de-vigged",
                },
                "recency_policy": {
                    "half_life_days": half_life,
                    "selection_provenance": selection_provenance(half_life),
                    "historical_audit_status": "exploratory_previously_observed_data",
                    "betting_rule": None,
                    "stake_rule": None,
                    "result_model_weight": 0.0,
                },
                "features": asdict(feature_row),
            }
            record["content_sha256"] = content_hash(record)
            records.append(record)

    records.sort(key=lambda row: (row["commence_time_utc"], row["event_id"]))
    return records, {
        "model_id": shadow_model_id,
        "half_life_days": half_life,
        "decision_weight": DECISION_WEIGHT,
        "locked_at_utc": locked_at_utc,
        "source_records": len(source_records),
        "created_records": len(records),
        "skipped_already_started": skipped_started,
    }


def append_shadow_records(path: Path, records: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if path.exists():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            stored = row.get("content_sha256")
            unsigned = dict(row)
            unsigned.pop("content_sha256", None)
            if stored != content_hash(unsigned):
                raise ValueError(f"Shadow ledger line {line_number} failed content hash verification")
            existing.add(str(row["record_id"]))
    additions = [row for row in records if str(row["record_id"]) not in existing]
    if additions:
        with path.open("a", encoding="utf-8") as handle:
            for row in additions:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    return len(additions)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lock a zero-weight recency prospective shadow.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--source-ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("prospective/recency_shadow.jsonl"))
    parser.add_argument("--locked-at-utc", required=True)
    parser.add_argument("--half-life-days", type=float, default=DEFAULT_HALF_LIFE_DAYS)
    parser.add_argument("--model-id")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    source = load_source_records(args.source_ledger)
    records, metadata = build_shadow_records(
        args.database,
        source,
        locked_at_utc=args.locked_at_utc,
        half_life_days=args.half_life_days,
        model_id=args.model_id,
    )
    added = append_shadow_records(args.output, records)
    print(json.dumps({**metadata, "appended_records": added}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
