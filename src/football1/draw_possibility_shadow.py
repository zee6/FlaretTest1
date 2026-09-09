from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from football1.draw_possibility_audit import FIXED_BALANCE_THRESHOLDS
from football1.features import build_feature_rows
from football1.market_baseline import devig_decimal_odds
from football1.prospective import _parse_utc, prediction_content_hash


MODEL_ID = "draw_possibility_market_balance_percentile_v1"
DECISION_WEIGHT = 0.0


def content_hash(record_without_hash: dict[str, Any]) -> str:
    encoded = json.dumps(record_without_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_source_records(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        stored = row.get("content_sha256")
        unsigned = dict(row)
        unsigned.pop("content_sha256", None)
        if stored != prediction_content_hash(unsigned):
            raise ValueError(f"Source ledger line {line_number} failed content hash verification")
        rows.append(row)
    return rows


def historical_market_gaps(db_path: Path) -> list[float]:
    gaps: list[float] = []
    for row in build_feature_rows(db_path):
        if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
            continue
        probs, _ = devig_decimal_odds((float(row.b365_home), float(row.b365_draw), float(row.b365_away)))
        gaps.append(abs(float(probs[0]) - float(probs[2])))
    if not gaps:
        raise ValueError("No historical market gaps available")
    return sorted(gaps)


def possibility_percentile(gap: float, historical_gaps: list[float]) -> float:
    if not math.isfinite(gap) or gap < 0.0 or gap > 1.0:
        raise ValueError("gap must be finite and between zero and one")
    if not historical_gaps:
        raise ValueError("historical_gaps must not be empty")
    if any((not math.isfinite(x)) or x < 0.0 or x > 1.0 for x in historical_gaps):
        raise ValueError("historical_gaps contains invalid values")
    # Higher score means more balanced than a larger share of historical matches.
    at_least_as_wide = sum(1 for x in historical_gaps if x >= gap)
    return 100.0 * at_least_as_wide / len(historical_gaps)


def _source_market_probabilities(source: dict[str, Any]) -> tuple[float, float, float]:
    raw = source["market_anchor"]["probability"]
    values = (float(raw["home"]), float(raw["draw"]), float(raw["away"]))
    if any((not math.isfinite(x)) or x <= 0.0 or x >= 1.0 for x in values):
        raise ValueError("source market probability contains invalid values")
    if not math.isclose(sum(values), 1.0, abs_tol=1e-6):
        raise ValueError("source market probabilities must sum to one")
    return values


def build_shadow_records(
    db_path: Path,
    source_records: list[dict[str, Any]],
    *,
    locked_at_utc: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    locked_at = _parse_utc(locked_at_utc)
    future = [row for row in source_records if _parse_utc(str(row["commence_time_utc"])) > locked_at]
    historical_gaps = historical_market_gaps(db_path) if future else []
    records: list[dict[str, Any]] = []

    for source in future:
        p_home, p_draw, p_away = _source_market_probabilities(source)
        gap = abs(p_home - p_away)
        percentile = possibility_percentile(gap, historical_gaps)
        identity = "|".join([str(source["record_id"]), MODEL_ID]).encode("utf-8")
        flags = {
            f"within_{int(round(threshold * 100))}pp": gap <= threshold
            for threshold in FIXED_BALANCE_THRESHOLDS
        }
        record: dict[str, Any] = {
            "schema_version": 1,
            "record_id": hashlib.sha256(identity).hexdigest()[:24],
            "status": "draw_possibility_shadow_locked",
            "model_id": MODEL_ID,
            "decision_weight": DECISION_WEIGHT,
            "event_id": source["event_id"],
            "commence_time_utc": source["commence_time_utc"],
            "shadow_locked_at_utc": locked_at_utc,
            "teams": {
                "home": source["home_team_canonical"],
                "away": source["away_team_canonical"],
            },
            "source_prediction": {
                "record_id": source["record_id"],
                "content_sha256": source["content_sha256"],
                "snapshot_retrieved_at_utc": source["snapshot_retrieved_at_utc"],
                "market_anchor_type": source["market_anchor"]["type"],
            },
            "market_probability": {
                "home": p_home,
                "draw": p_draw,
                "away": p_away,
            },
            "draw_possibility": {
                "home_away_probability_gap": gap,
                "balance_percentile_0_to_100": percentile,
                "higher_percentile_means": "more balanced than a larger share of historical EPL market shapes",
                "is_probability": False,
                "fixed_predeclared_balance_flags": flags,
            },
            "historical_reference": {
                "matches": len(historical_gaps),
                "market_anchor": "B365 pre-closing de-vigged",
                "database_scope": "frozen 4 September 2026 canonical EPL history",
            },
            "policy": {
                "betting_rule": None,
                "stake_rule": None,
                "draw_probability_adjustment": None,
                "selection_threshold": None,
                "result_model_weight": 0.0,
                "historical_status": "post_hoc_historical_clue_prospective_confirmation_only",
            },
        }
        record["content_sha256"] = content_hash(record)
        records.append(record)

    records.sort(key=lambda row: (row["commence_time_utc"], row["event_id"]))
    return records, {
        "model_id": MODEL_ID,
        "decision_weight": DECISION_WEIGHT,
        "locked_at_utc": locked_at_utc,
        "source_records": len(source_records),
        "created_records": len(records),
        "skipped_already_started": len(source_records) - len(future),
        "historical_reference_matches": len(historical_gaps),
    }


def append_shadow_records(path: Path, records: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
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
            existing_ids.add(str(row["record_id"]))
    additions = [row for row in records if str(row["record_id"]) not in existing_ids]
    if additions:
        with path.open("a", encoding="utf-8") as handle:
            for row in additions:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    return len(additions)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lock a zero-weight prospective Draw Possibility shadow.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--source-ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("prospective/draw_possibility_shadow.jsonl"))
    parser.add_argument("--locked-at-utc", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    source = load_source_records(args.source_ledger)
    records, metadata = build_shadow_records(args.database, source, locked_at_utc=args.locked_at_utc)
    added = append_shadow_records(args.output, records)
    print(json.dumps({**metadata, "appended_records": added}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
