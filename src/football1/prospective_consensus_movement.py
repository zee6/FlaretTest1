from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football1.closing_movement_rf import _movement_error_summary
from football1.features import feature_vector
from football1.market_baseline import devig_decimal_odds
from football1.market_consensus_baseline_check import mean_movement
from football1.market_consensus_movement import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_FEATURES,
    DEFAULT_MIN_SAMPLES_LEAF,
    DEFAULT_N_ESTIMATORS,
    DEFAULT_RANDOM_STATE,
    _fit,
    actual_movement,
    best_price_premium,
    build_market_consensus_observations,
)
from football1.odds_archive import normalize_snapshot
from football1.prospective import _live_feature_row, _states_as_of


LABELS = ("home", "draw", "away")
MODEL_SUITE_ID = "historical_average_market_closing_movement_rf_v1_prospective_shadow"
SCHEMA_VERSION = 1
MIN_COMMON_BOOKMAKERS = 2
FORECAST_NAMES = ("zero_movement", "training_mean_movement", "base_rf", "rf_plus_best_price_premium")


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"Timestamp must include timezone: {value}")
    return dt.astimezone(timezone.utc)


def movement_forecast_content_hash(record_without_hash: dict[str, Any]) -> str:
    encoded = json.dumps(record_without_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _movement_dict(values: tuple[float, float, float]) -> dict[str, float]:
    if abs(sum(values)) > 1e-9:
        raise ValueError("Movement vector must sum to zero")
    return dict(zip(LABELS, values, strict=True))


def _movement_tuple(raw: dict[str, Any]) -> tuple[float, float, float]:
    values = tuple(float(raw[label]) for label in LABELS)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Movement vector must contain finite values")
    if abs(sum(values)) > 1e-7:
        raise ValueError("Movement vector must sum to zero")
    return values  # type: ignore[return-value]


def bookmaker_market_shape(bookmakers: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a Football-Data-like Avg/Max market shape from complete bookmaker quotes."""
    if not bookmakers:
        raise ValueError("At least one complete bookmaker quote is required")
    average = tuple(
        statistics.fmean(float(row["decimal_odds"][label]) for row in bookmakers)
        for label in LABELS
    )
    maximum = tuple(
        max(float(row["decimal_odds"][label]) for row in bookmakers)
        for label in LABELS
    )
    if any(not math.isfinite(value) or value <= 1.0 for value in average + maximum):
        raise ValueError("Bookmaker decimal odds must be finite and greater than 1")
    probability = devig_decimal_odds(average)[0]
    premium = best_price_premium(average, maximum)
    return {
        "bookmaker_count": len(bookmakers),
        "average_decimal_odds": dict(zip(LABELS, average, strict=True)),
        "maximum_decimal_odds": dict(zip(LABELS, maximum, strict=True)),
        "average_odds_devigged_probability": dict(zip(LABELS, probability, strict=True)),
        "best_price_premium": dict(zip(LABELS, premium, strict=True)),
    }


def _predict_vector(model: Any, vector: list[float]) -> tuple[float, float, float]:
    raw = [float(value) for value in model.predict([vector])[0]]
    mean = sum(raw) / 3.0
    centered = tuple(value - mean for value in raw)
    return (centered[0], centered[1], centered[2])


def _selected_outcome(predicted: tuple[float, float, float]) -> str:
    return LABELS[max(range(3), key=lambda i: predicted[i])]


def make_movement_forecast_record(
    *,
    event: dict[str, Any],
    snapshot_retrieved_at_utc: str,
    training_matches: int,
    training_seasons: list[int],
    historical_data_cutoff: str | None,
    live_market_shape: dict[str, Any],
    training_mean: tuple[float, float, float],
    base_move: tuple[float, float, float],
    augmented_move: tuple[float, float, float],
    features: dict[str, Any],
) -> dict[str, Any]:
    retrieved = _parse_utc(snapshot_retrieved_at_utc)
    kickoff = _parse_utc(str(event["commence_time_utc"]))
    if kickoff <= retrieved:
        raise ValueError("Prospective movement forecast must be locked before kickoff")

    zero = (0.0, 0.0, 0.0)
    forecasts = {
        "zero_movement": {
            "movement": _movement_dict(zero),
            "selected_outcome": None,
        },
        "training_mean_movement": {
            "movement": _movement_dict(training_mean),
            "selected_outcome": _selected_outcome(training_mean),
        },
        "base_rf": {
            "movement": _movement_dict(base_move),
            "selected_outcome": _selected_outcome(base_move),
        },
        "rf_plus_best_price_premium": {
            "movement": _movement_dict(augmented_move),
            "selected_outcome": _selected_outcome(augmented_move),
        },
    }
    identity_seed = "|".join(
        [str(event["event_id"]), snapshot_retrieved_at_utc, MODEL_SUITE_ID]
    ).encode("utf-8")
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "record_id": hashlib.sha256(identity_seed).hexdigest()[:24],
        "status": "market_movement_forecast_locked",
        "model_suite_id": MODEL_SUITE_ID,
        "decision_weight": 0.0,
        "provider": str(event.get("provider") or "the-odds-api"),
        "sport_key": str(event.get("sport_key") or "soccer_epl"),
        "event_id": event["event_id"],
        "commence_time_utc": event["commence_time_utc"],
        "snapshot_retrieved_at_utc": snapshot_retrieved_at_utc,
        "home_team_provider": event["home_team"],
        "away_team_provider": event["away_team"],
        "historical_training": {
            "matches": training_matches,
            "seasons": training_seasons,
            "historical_data_cutoff": historical_data_cutoff,
            "target": "closing average-market de-vigged probability minus first average-market de-vigged probability",
            "same_day_policy": "exclude historical matches whose match_date is the snapshot UTC date",
        },
        "live_market_anchor": {
            **live_market_shape,
            "construction": "arithmetic mean and maximum decimal odds across complete H/D/A books in this snapshot; mean triplet is de-vigged after averaging",
            "historical_analogy": "Football-Data AvgH/AvgD/AvgA and MaxH/MaxD/MaxA",
            "anchor_change_status": "prospective provider/bookmaker universe differs from historical Football-Data aggregates",
        },
        "forecasts": forecasts,
        "features": features,
        "policy": {
            "purpose": "prospective price-movement and CLV observation only",
            "betting_rule": None,
            "movement_threshold": None,
            "stake_rule": None,
            "result_model_weight": 0.0,
        },
        "rf_hyperparameters": {
            "n_estimators": DEFAULT_N_ESTIMATORS,
            "max_depth": DEFAULT_MAX_DEPTH,
            "min_samples_leaf": DEFAULT_MIN_SAMPLES_LEAF,
            "max_features": DEFAULT_MAX_FEATURES,
            "random_state": DEFAULT_RANDOM_STATE,
        },
    }
    record["content_sha256"] = movement_forecast_content_hash(record)
    return record


def build_prospective_movement_forecasts(
    db_path: Path,
    snapshot: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    retrieved_at = str(snapshot["retrieved_at_utc"])
    retrieved = _parse_utc(retrieved_at)
    cutoff_date = retrieved.date().isoformat()

    historical = [
        obs
        for obs in build_market_consensus_observations(db_path)
        if obs.base.match_date < cutoff_date
    ]
    if not historical:
        raise ValueError("No historical average-market movement observations before snapshot")
    training_seasons = sorted({obs.season_start_year for obs in historical})
    if len(training_seasons) < 3:
        raise ValueError("At least three historical seasons are required")

    base_model = _fit(historical, augmented=False)
    augmented_model = _fit(historical, augmented=True)
    training_mean = mean_movement([actual_movement(obs) for obs in historical])
    states, historical_cutoff = _states_as_of(db_path, cutoff_date)
    normalized = normalize_snapshot(snapshot)

    records: list[dict[str, Any]] = []
    skipped_unknown_team = 0
    for event in normalized:
        try:
            feature_row = _live_feature_row(
                event_id=str(event["event_id"]),
                commence_time=str(event["commence_time_utc"]),
                home_team=str(event["home_team"]),
                away_team=str(event["away_team"]),
                states=states,
            )
        except ValueError:
            skipped_unknown_team += 1
            continue

        shape = bookmaker_market_shape(list(event["bookmakers"]))
        average_odds = tuple(float(shape["average_decimal_odds"][label]) for label in LABELS)
        maximum_odds = tuple(float(shape["maximum_decimal_odds"][label]) for label in LABELS)
        opening_probability = devig_decimal_odds(average_odds)[0]
        premium = best_price_premium(average_odds, maximum_odds)
        base_vector = feature_vector(feature_row) + list(opening_probability)
        augmented_vector = base_vector + list(premium)
        base_move = _predict_vector(base_model, base_vector)
        augmented_move = _predict_vector(augmented_model, augmented_vector)

        records.append(
            make_movement_forecast_record(
                event=event,
                snapshot_retrieved_at_utc=retrieved_at,
                training_matches=len(historical),
                training_seasons=training_seasons,
                historical_data_cutoff=historical_cutoff,
                live_market_shape=shape,
                training_mean=training_mean,
                base_move=base_move,
                augmented_move=augmented_move,
                features={
                    "home_team_canonical": feature_row.home_team,
                    "away_team_canonical": feature_row.away_team,
                    "feature_vector": feature_vector(feature_row),
                },
            )
        )

    records.sort(key=lambda row: (row["commence_time_utc"], row["event_id"]))
    return records, {
        "snapshot_retrieved_at_utc": retrieved_at,
        "historical_data_cutoff": historical_cutoff,
        "training_matches": len(historical),
        "training_seasons": training_seasons,
        "created_records": len(records),
        "skipped_unknown_team": skipped_unknown_team,
        "model_suite_id": MODEL_SUITE_ID,
        "decision_weight": 0.0,
    }


def append_movement_forecast_records(path: Path, records: list[dict[str, Any]]) -> int:
    """Append at most the earliest immutable movement lock per event/model suite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_keys: set[tuple[str, str]] = set()
    existing_ids: set[str] = set()

    if path.exists():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            stored = row.get("content_sha256")
            unsigned = dict(row)
            unsigned.pop("content_sha256", None)
            if stored != movement_forecast_content_hash(unsigned):
                raise ValueError(f"Movement forecast ledger line {line_number} failed content hash verification")
            event_id = str(row.get("event_id") or "")
            suite_id = str(row.get("model_suite_id") or "")
            if not event_id or not suite_id:
                raise ValueError(f"Movement forecast ledger line {line_number} is missing lock identity")
            existing_keys.add((event_id, suite_id))
            existing_ids.add(str(row.get("record_id") or ""))

    new_records: list[dict[str, Any]] = []
    pending: set[tuple[str, str]] = set()
    for record in records:
        stored = record.get("content_sha256")
        unsigned = dict(record)
        unsigned.pop("content_sha256", None)
        if stored != movement_forecast_content_hash(unsigned):
            raise ValueError("New movement forecast record failed content hash verification")
        key = (str(record["event_id"]), str(record["model_suite_id"]))
        if str(record["record_id"]) in existing_ids or key in existing_keys or key in pending:
            continue
        pending.add(key)
        new_records.append(record)

    if not new_records:
        return 0
    with path.open("a", encoding="utf-8") as handle:
        for record in new_records:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return len(new_records)


def load_movement_forecast_locks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        stored = row.get("content_sha256")
        unsigned = dict(row)
        unsigned.pop("content_sha256", None)
        if stored != movement_forecast_content_hash(unsigned):
            raise ValueError(f"Movement forecast ledger line {line_number} failed content hash verification")
        if row.get("status") == "market_movement_forecast_locked":
            rows.append(row)
    return rows


def _quotes_by_key(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for quote in snapshot.get("bookmakers", []):
        key = str(quote.get("bookmaker_key") or "")
        if key:
            result[key] = quote
    return result


def common_book_market_pair(
    initial: dict[str, Any],
    later: dict[str, Any],
    *,
    min_common_bookmakers: int = MIN_COMMON_BOOKMAKERS,
) -> dict[str, Any] | None:
    """Measure movement on a fixed common bookmaker set to avoid composition drift."""
    first = _quotes_by_key(initial)
    second = _quotes_by_key(later)
    common = sorted(set(first) & set(second))
    if len(common) < min_common_bookmakers:
        return None
    initial_quotes = [first[key] for key in common]
    later_quotes = [second[key] for key in common]
    initial_shape = bookmaker_market_shape(initial_quotes)
    later_shape = bookmaker_market_shape(later_quotes)
    initial_prob = tuple(
        float(initial_shape["average_odds_devigged_probability"][label]) for label in LABELS
    )
    later_prob = tuple(
        float(later_shape["average_odds_devigged_probability"][label]) for label in LABELS
    )
    movement = tuple(later_prob[i] - initial_prob[i] for i in range(3))
    return {
        "common_bookmaker_keys": common,
        "common_bookmaker_count": len(common),
        "initial": initial_shape,
        "later": later_shape,
        "actual_movement": dict(zip(LABELS, movement, strict=True)),
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _price_timing_summary(
    event_rows: list[dict[str, Any]],
    forecast_name: str,
) -> dict[str, Any]:
    if forecast_name == "zero_movement":
        return {
            "matches": len(event_rows),
            "selection_rule": None,
            "fraction_selected_outcome_actually_shortened": None,
            "mean_actual_probability_move_selected_outcome": None,
            "mean_initial_vs_later_average_price_ratio": None,
            "mean_initial_vs_later_best_price_ratio_common_books": None,
        }
    if not event_rows:
        return {
            "matches": 0,
            "selection_rule": "choose the outcome with the largest frozen predicted rise in probability; no size threshold",
            "fraction_selected_outcome_actually_shortened": None,
            "mean_actual_probability_move_selected_outcome": None,
            "mean_initial_vs_later_average_price_ratio": None,
            "mean_initial_vs_later_best_price_ratio_common_books": None,
        }

    shortened = 0
    actual_selected: list[float] = []
    average_ratios: list[float] = []
    best_ratios: list[float] = []
    for row in event_rows:
        predicted = row["predicted"][forecast_name]
        selected = max(range(3), key=lambda i: predicted[i])
        actual = row["actual"][selected]
        actual_selected.append(actual)
        if actual > 0.0:
            shortened += 1
        first_avg = row["initial_average_odds"][selected]
        later_avg = row["later_average_odds"][selected]
        first_best = row["initial_best_odds"][selected]
        later_best = row["later_best_odds"][selected]
        average_ratios.append(first_avg / later_avg - 1.0)
        best_ratios.append(first_best / later_best - 1.0)

    return {
        "matches": len(event_rows),
        "selection_rule": "choose the outcome with the largest frozen predicted rise in de-vigged common-book average-market probability; no movement-size threshold",
        "fraction_selected_outcome_actually_shortened": shortened / len(event_rows),
        "mean_actual_probability_move_selected_outcome": _mean(actual_selected),
        "mean_initial_vs_later_average_price_ratio": _mean(average_ratios),
        "mean_initial_vs_later_best_price_ratio_common_books": _mean(best_ratios),
        "price_ratio_definition": "initial decimal odds / later decimal odds - 1; positive means the earlier price was longer",
        "warning": "prospective price-timing diagnostic only; no bet, stake or result edge is inferred",
    }


def build_prospective_movement_report(
    lock_rows: list[dict[str, Any]],
    odds_rows: list[dict[str, Any]],
    *,
    min_common_bookmakers: int = MIN_COMMON_BOOKMAKERS,
) -> dict[str, Any]:
    snapshots_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in odds_rows:
        if row.get("status") != "pre_kickoff_odds_snapshot":
            continue
        event_id = str(row.get("event_id") or "")
        if event_id:
            snapshots_by_event[event_id].append(row)
    for rows in snapshots_by_event.values():
        rows.sort(key=lambda row: _parse_utc(str(row["retrieved_at_utc"])))

    event_rows: list[dict[str, Any]] = []
    skipped_no_initial = 0
    skipped_no_later = 0
    skipped_common_books = 0

    for lock in lock_rows:
        event_id = str(lock["event_id"])
        lock_time = _parse_utc(str(lock["snapshot_retrieved_at_utc"]))
        kickoff = _parse_utc(str(lock["commence_time_utc"]))
        snapshots = snapshots_by_event.get(event_id, [])
        initial = next(
            (row for row in snapshots if _parse_utc(str(row["retrieved_at_utc"])) == lock_time),
            None,
        )
        if initial is None:
            skipped_no_initial += 1
            continue
        later = [
            row
            for row in snapshots
            if lock_time < _parse_utc(str(row["retrieved_at_utc"])) < kickoff
        ]
        if not later:
            skipped_no_later += 1
            continue
        latest = later[-1]
        pair = common_book_market_pair(
            initial,
            latest,
            min_common_bookmakers=min_common_bookmakers,
        )
        if pair is None:
            skipped_common_books += 1
            continue

        actual = tuple(float(pair["actual_movement"][label]) for label in LABELS)
        predicted = {
            name: _movement_tuple(lock["forecasts"][name]["movement"])
            for name in FORECAST_NAMES
        }
        initial_avg = tuple(float(pair["initial"]["average_decimal_odds"][label]) for label in LABELS)
        later_avg = tuple(float(pair["later"]["average_decimal_odds"][label]) for label in LABELS)
        initial_best = tuple(float(pair["initial"]["maximum_decimal_odds"][label]) for label in LABELS)
        later_best = tuple(float(pair["later"]["maximum_decimal_odds"][label]) for label in LABELS)

        event_rows.append(
            {
                "event_id": event_id,
                "home_team": lock.get("home_team_provider"),
                "away_team": lock.get("away_team_provider"),
                "commence_time_utc": lock["commence_time_utc"],
                "locked_at_utc": lock["snapshot_retrieved_at_utc"],
                "later_market_at_utc": latest["retrieved_at_utc"],
                "common_bookmaker_keys": pair["common_bookmaker_keys"],
                "common_bookmaker_count": pair["common_bookmaker_count"],
                "actual_movement": dict(zip(LABELS, actual, strict=True)),
                "predicted_movement": {
                    name: dict(zip(LABELS, predicted[name], strict=True)) for name in FORECAST_NAMES
                },
            }
        )
        event_rows[-1]["_scoring"] = {
            "actual": actual,
            "predicted": predicted,
            "initial_average_odds": initial_avg,
            "later_average_odds": later_avg,
            "initial_best_odds": initial_best,
            "later_best_odds": later_best,
        }

    scoring_rows = [row["_scoring"] for row in event_rows]
    blocks: dict[str, Any] = {}
    for name in FORECAST_NAMES:
        actual = [row["actual"] for row in scoring_rows]
        predicted = [row["predicted"][name] for row in scoring_rows]
        blocks[name] = {
            **_movement_error_summary(actual, predicted),
            "price_timing": _price_timing_summary(scoring_rows, name),
        }

    def delta(model: str, baseline: str, metric: str) -> float | None:
        a = blocks[model].get(metric)
        b = blocks[baseline].get(metric)
        if a is None or b is None:
            return None
        return float(a) - float(b)

    for row in event_rows:
        row.pop("_scoring", None)

    return {
        "observer": "prospective_historical_average_market_closing_movement_rf_v1",
        "status": (
            "prospective_price_movement_observer_zero_decision_weight"
            if event_rows
            else "awaiting_later_common_book_price_snapshots_zero_decision_weight"
        ),
        "decision_policy": (
            "Observer only. Forecasts are frozen before kickoff and never alter result probabilities, "
            "betting thresholds, stake suitability or retrospective selection rules."
        ),
        "evaluation_policy": (
            f"Score against the latest archived snapshot after the lock and before kickoff using at least "
            f"{min_common_bookmakers} bookmakers present in both snapshots. Average and maximum odds are "
            "recomputed on that fixed common-book set so bookmaker entry/exit cannot masquerade as price movement."
        ),
        "locked_forecasts": len(lock_rows),
        "matches_scored": len(event_rows),
        "coverage_rate": len(event_rows) / len(lock_rows) if lock_rows else None,
        "skipped_no_initial_archive_snapshot": skipped_no_initial,
        "skipped_no_later_snapshot": skipped_no_later,
        "skipped_insufficient_common_bookmakers": skipped_common_books,
        "overall": {
            **blocks,
            "base_rf_mae_delta_vs_training_mean": delta(
                "base_rf", "training_mean_movement", "mean_abs_error_per_outcome"
            ),
            "base_rf_rmse_delta_vs_training_mean": delta(
                "base_rf", "training_mean_movement", "rmse_per_outcome"
            ),
            "augmented_rf_mae_delta_vs_training_mean": delta(
                "rf_plus_best_price_premium", "training_mean_movement", "mean_abs_error_per_outcome"
            ),
            "augmented_rf_rmse_delta_vs_training_mean": delta(
                "rf_plus_best_price_premium", "training_mean_movement", "rmse_per_outcome"
            ),
            "augmented_rf_mae_delta_vs_base_rf": delta(
                "rf_plus_best_price_premium", "base_rf", "mean_abs_error_per_outcome"
            ),
            "augmented_rf_rmse_delta_vs_base_rf": delta(
                "rf_plus_best_price_premium", "base_rf", "rmse_per_outcome"
            ),
        },
        "events": event_rows,
    }


def prospective_movement_report(
    ledger_path: Path,
    odds_path: Path,
    *,
    min_common_bookmakers: int = MIN_COMMON_BOOKMAKERS,
) -> dict[str, Any]:
    from football1.market_movement_observer import load_odds_snapshots

    locks = load_movement_forecast_locks(ledger_path)
    odds = load_odds_snapshots(odds_path)
    return build_prospective_movement_report(
        locks,
        odds,
        min_common_bookmakers=min_common_bookmakers,
    )


def build_lock_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append frozen prospective EPL closing-movement forecasts from the historical consensus RF."
    )
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--snapshot", type=Path, default=Path("data/live/epl_odds_snapshot.json"))
    parser.add_argument("--ledger", type=Path, default=Path("prospective/movement_predictions.jsonl"))
    return parser


def lock_main() -> None:
    args = build_lock_parser().parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    records, metadata = build_prospective_movement_forecasts(args.database, snapshot)
    appended = append_movement_forecast_records(args.ledger, records)
    metadata["appended_records"] = appended
    metadata["ledger"] = str(args.ledger)
    print(json.dumps(metadata, sort_keys=True))


def build_report_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score frozen EPL market-movement forecasts against later common-book pre-kickoff prices."
    )
    parser.add_argument("--ledger", type=Path, default=Path("prospective/movement_predictions.jsonl"))
    parser.add_argument("--odds-archive", type=Path, default=Path("prospective/odds_snapshots.jsonl"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-common-bookmakers", type=int, default=MIN_COMMON_BOOKMAKERS)
    return parser


def report_main() -> None:
    args = build_report_parser().parse_args()
    if args.min_common_bookmakers < 1:
        raise ValueError("--min-common-bookmakers must be at least 1")
    report = prospective_movement_report(
        args.ledger,
        args.odds_archive,
        min_common_bookmakers=args.min_common_bookmakers,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote prospective movement forecast report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    lock_main()
