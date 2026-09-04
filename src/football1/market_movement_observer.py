from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football1.odds_archive import odds_record_hash
from football1.prospective import prediction_content_hash


LABELS = ("home", "draw", "away")


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"Timestamp must include timezone: {value}")
    return dt.astimezone(timezone.utc)


def _triple(raw: dict[str, Any]) -> tuple[float, float, float]:
    values = tuple(float(raw[label]) for label in LABELS)
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ValueError("Probability triple must contain positive finite values")
    if abs(sum(values) - 1.0) > 1e-6:
        raise ValueError("Probability triple must sum to 1")
    return values  # type: ignore[return-value]


def _verify_prediction(row: dict[str, Any], line_number: int | None = None) -> None:
    stored = row.get("content_sha256")
    unsigned = dict(row)
    unsigned.pop("content_sha256", None)
    if stored != prediction_content_hash(unsigned):
        where = f" line {line_number}" if line_number is not None else ""
        raise ValueError(f"Prediction ledger{where} failed content hash verification")


def _verify_odds(row: dict[str, Any], line_number: int | None = None) -> None:
    stored = row.get("content_sha256")
    unsigned = dict(row)
    unsigned.pop("content_sha256", None)
    if stored != odds_record_hash(unsigned):
        where = f" line {line_number}" if line_number is not None else ""
        raise ValueError(f"Odds archive{where} failed content hash verification")


def _load_jsonl(path: Path, *, kind: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{kind} line {line_number} is not a JSON object")
        if kind == "prediction":
            _verify_prediction(row, line_number)
        elif kind == "odds":
            _verify_odds(row, line_number)
        else:
            raise ValueError(f"Unknown JSONL kind: {kind}")
        rows.append(row)
    return rows


def load_prediction_locks(path: Path) -> list[dict[str, Any]]:
    return _load_jsonl(path, kind="prediction")


def load_odds_snapshots(path: Path) -> list[dict[str, Any]]:
    return _load_jsonl(path, kind="odds")


def _model_id(row: dict[str, Any]) -> str:
    model = row.get("model")
    if not isinstance(model, dict):
        return ""
    return str(model.get("id") or "")


def _earliest_prediction_locks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first historical lock for each event/model pair.

    New writes already enforce this invariant. Selecting the earliest lock here
    also makes the observer safe if an older ledger contains repeated snapshots
    created before that invariant existed.
    """
    earliest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != "prediction_locked":
            continue
        event_id = str(row.get("event_id") or "")
        model_id = _model_id(row)
        if not event_id or not model_id:
            continue
        key = (event_id, model_id)
        existing = earliest.get(key)
        if existing is None or _parse_utc(str(row["snapshot_retrieved_at_utc"])) < _parse_utc(
            str(existing["snapshot_retrieved_at_utc"])
        ):
            earliest[key] = row
    return sorted(
        earliest.values(),
        key=lambda row: (
            _parse_utc(str(row["snapshot_retrieved_at_utc"])),
            str(row["event_id"]),
            _model_id(row),
        ),
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _finite_dispersion_mean(snapshot: dict[str, Any]) -> float | None:
    raw = snapshot.get("fair_probability_dispersion")
    if not isinstance(raw, dict):
        return None
    values: list[float] = []
    for label in LABELS:
        value = raw.get(label)
        if value is None:
            continue
        number = float(value)
        if math.isfinite(number):
            values.append(number)
    return _mean(values)


def build_market_movement_report(
    prediction_rows: list[dict[str, Any]],
    odds_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare later pre-kickoff market prices with the immutable Football 1 lock.

    The locked prediction's market probability is time zero. An odds snapshot is
    eligible only when it is strictly later than the lock and strictly before
    kickoff. Nothing in this observer changes a prediction, bet view or stake.
    """
    locks = _earliest_prediction_locks(prediction_rows)
    snapshots_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in odds_rows:
        if row.get("status") != "pre_kickoff_odds_snapshot":
            continue
        event_id = str(row.get("event_id") or "")
        if event_id:
            snapshots_by_event[event_id].append(row)
    for snapshots in snapshots_by_event.values():
        snapshots.sort(key=lambda row: _parse_utc(str(row["retrieved_at_utc"])))

    event_reports: list[dict[str, Any]] = []
    for lock in locks:
        event_id = str(lock["event_id"])
        lock_time = _parse_utc(str(lock["snapshot_retrieved_at_utc"]))
        kickoff = _parse_utc(str(lock["commence_time_utc"]))
        eligible = [
            row
            for row in snapshots_by_event.get(event_id, [])
            if lock_time < _parse_utc(str(row["retrieved_at_utc"])) < kickoff
        ]
        if not eligible:
            continue

        latest = eligible[-1]
        model = _triple(lock["model"]["probability"])
        initial_market = _triple(lock["market_anchor"]["probability"])
        final_market = _triple(latest["consensus_fair_probability"])
        residual = tuple(model[i] - initial_market[i] for i in range(3))
        movement = tuple(final_market[i] - initial_market[i] for i in range(3))
        initial_l1 = sum(abs(value) for value in residual)
        final_l1 = sum(abs(model[i] - final_market[i]) for i in range(3))
        l1_reduction = initial_l1 - final_l1
        directional_dot = sum(residual[i] * movement[i] for i in range(3))
        mean_abs_market_move = sum(abs(value) for value in movement) / 3.0
        call_index = max(range(3), key=lambda i: model[i])
        call_alignment = residual[call_index] * movement[call_index]

        event_reports.append(
            {
                "event_id": event_id,
                "model_id": _model_id(lock),
                "home_team": lock.get("home_team_provider"),
                "away_team": lock.get("away_team_provider"),
                "commence_time_utc": lock["commence_time_utc"],
                "locked_at_utc": lock["snapshot_retrieved_at_utc"],
                "latest_market_at_utc": latest["retrieved_at_utc"],
                "later_snapshots": len(eligible),
                "model_probability": dict(zip(LABELS, model)),
                "locked_market_probability": dict(zip(LABELS, initial_market)),
                "latest_market_probability": dict(zip(LABELS, final_market)),
                "market_move": dict(zip(LABELS, movement)),
                "initial_model_market_residual": dict(zip(LABELS, residual)),
                "initial_l1_distance": initial_l1,
                "latest_l1_distance": final_l1,
                "l1_distance_reduction": l1_reduction,
                "market_is_closer_to_model": l1_reduction > 0.0,
                "directional_dot_product": directional_dot,
                "movement_direction_aligns_with_model": directional_dot > 0.0,
                "mean_abs_market_probability_move": mean_abs_market_move,
                "model_call": LABELS[call_index],
                "model_call_market_move": movement[call_index],
                "model_call_direction_alignment": call_alignment,
                "model_call_market_moved_toward": call_alignment > 0.0,
                "latest_cross_book_dispersion_mean": _finite_dispersion_mean(latest),
            }
        )

    n = len(event_reports)
    status = (
        "prospective_market_movement_observer_zero_decision_weight"
        if n
        else "awaiting_later_price_snapshots_zero_decision_weight"
    )
    closer = sum(1 for row in event_reports if row["market_is_closer_to_model"])
    aligned = sum(1 for row in event_reports if row["movement_direction_aligns_with_model"])
    call_toward = sum(1 for row in event_reports if row["model_call_market_moved_toward"])
    dispersions = [
        float(row["latest_cross_book_dispersion_mean"])
        for row in event_reports
        if row["latest_cross_book_dispersion_mean"] is not None
    ]

    return {
        "observer": "prospective_market_movement_toward_locked_football1_v1",
        "status": status,
        "decision_policy": (
            "Observer only. Later market prices never rewrite the locked Football 1 prediction "
            "and do not alter probability weight, betting thresholds or stake suitability."
        ),
        "selection_policy": (
            "Use the earliest immutable prediction per event/model. Compare its locked market "
            "anchor with the latest archived consensus snapshot strictly after the lock and "
            "strictly before kickoff. No movement-size threshold is selected."
        ),
        "locked_predictions": len(locks),
        "matches_with_later_market_snapshot": n,
        "coverage_rate": n / len(locks) if locks else None,
        "overall": {
            "fraction_market_closer_to_football1": closer / n if n else None,
            "mean_l1_distance_reduction": _mean(
                [float(row["l1_distance_reduction"]) for row in event_reports]
            ),
            "fraction_movement_direction_aligned_with_football1": aligned / n if n else None,
            "mean_directional_dot_product": _mean(
                [float(row["directional_dot_product"]) for row in event_reports]
            ),
            "fraction_model_call_market_moved_toward": call_toward / n if n else None,
            "mean_abs_market_probability_move": _mean(
                [float(row["mean_abs_market_probability_move"]) for row in event_reports]
            ),
            "mean_later_snapshots_per_match": _mean(
                [float(row["later_snapshots"]) for row in event_reports]
            ),
            "mean_latest_cross_book_dispersion": _mean(dispersions),
        },
        "events": event_reports,
    }


def market_movement_report(ledger_path: Path, odds_path: Path) -> dict[str, Any]:
    predictions = load_prediction_locks(ledger_path)
    odds = load_odds_snapshots(odds_path)
    return build_market_movement_report(predictions, odds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Observe whether later pre-kickoff EPL market prices move toward locked Football 1 probabilities."
    )
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--odds-archive", type=Path, default=Path("prospective/odds_snapshots.jsonl"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = market_movement_report(args.ledger, args.odds_archive)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote prospective market movement observer to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
