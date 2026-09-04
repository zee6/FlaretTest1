from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


RESULT_INDEX = {"H": 0, "D": 1, "A": 2}


@dataclass(frozen=True)
class ProbabilityScores:
    log_loss: float
    brier: float
    correct: int


def odds_columns(source: str, phase: str) -> tuple[str, str, str]:
    if phase == "pre_closing":
        return (f"{source}H", f"{source}D", f"{source}A")
    if phase == "closing":
        return (f"{source}CH", f"{source}CD", f"{source}CA")
    raise ValueError("phase must be 'pre_closing' or 'closing'")


def devig_decimal_odds(odds: tuple[float, float, float]) -> tuple[tuple[float, float, float], float]:
    if any((not math.isfinite(x)) or x <= 1.0 for x in odds):
        raise ValueError(f"Invalid decimal odds: {odds!r}")
    implied = tuple(1.0 / x for x in odds)
    overround = sum(implied)
    probs = tuple(x / overround for x in implied)
    return probs, overround


def score_probabilities(probs: tuple[float, float, float], result: str) -> ProbabilityScores:
    if result not in RESULT_INDEX:
        raise ValueError(f"Unknown result: {result!r}")
    if any((not math.isfinite(p)) or p <= 0.0 or p >= 1.0 for p in probs):
        raise ValueError(f"Invalid probabilities: {probs!r}")
    if not math.isclose(sum(probs), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"Probabilities do not sum to 1: {probs!r}")

    target = RESULT_INDEX[result]
    log_loss = -math.log(probs[target])
    brier = sum((p - (1.0 if i == target else 0.0)) ** 2 for i, p in enumerate(probs))
    predicted = max(range(3), key=lambda i: probs[i])
    return ProbabilityScores(log_loss=log_loss, brier=brier, correct=int(predicted == target))


def _parse_triplet(row: dict[str, object], columns: tuple[str, str, str]) -> tuple[float, float, float] | None:
    try:
        values = tuple(float(str(row.get(c, "")).strip()) for c in columns)
    except (TypeError, ValueError):
        return None
    if any((not math.isfinite(x)) or x <= 1.0 for x in values):
        return None
    return values  # type: ignore[return-value]


def evaluate_market_baseline(db_path: Path, source: str, phase: str) -> dict[str, object]:
    columns = odds_columns(source, phase)
    conn = sqlite3.connect(db_path)
    try:
        records = conn.execute(
            """
            SELECT season_start_year, ftr, raw_json
            FROM matches
            ORDER BY match_date, match_id
            """
        ).fetchall()
    finally:
        conn.close()

    by_season: dict[int, dict[str, float | int]] = {}
    total_log_loss = 0.0
    total_brier = 0.0
    total_correct = 0
    total_overround = 0.0
    usable = 0

    for season_start_year, result, raw_json in records:
        raw = json.loads(raw_json)
        odds = _parse_triplet(raw, columns)
        if odds is None:
            continue
        probs, overround = devig_decimal_odds(odds)
        scores = score_probabilities(probs, result)

        usable += 1
        total_log_loss += scores.log_loss
        total_brier += scores.brier
        total_correct += scores.correct
        total_overround += overround

        bucket = by_season.setdefault(
            int(season_start_year),
            {"matches": 0, "log_loss_sum": 0.0, "brier_sum": 0.0, "correct": 0, "overround_sum": 0.0},
        )
        bucket["matches"] = int(bucket["matches"]) + 1
        bucket["log_loss_sum"] = float(bucket["log_loss_sum"]) + scores.log_loss
        bucket["brier_sum"] = float(bucket["brier_sum"]) + scores.brier
        bucket["correct"] = int(bucket["correct"]) + scores.correct
        bucket["overround_sum"] = float(bucket["overround_sum"]) + overround

    total_matches = len(records)
    season_rows: list[dict[str, object]] = []
    for season_start_year in sorted(by_season):
        bucket = by_season[season_start_year]
        n = int(bucket["matches"])
        season_rows.append(
            {
                "season_start_year": season_start_year,
                "matches": n,
                "log_loss": float(bucket["log_loss_sum"]) / n,
                "brier": float(bucket["brier_sum"]) / n,
                "accuracy": int(bucket["correct"]) / n,
                "mean_overround": float(bucket["overround_sum"]) / n,
            }
        )

    return {
        "source": source,
        "phase": phase,
        "columns": list(columns),
        "total_matches": total_matches,
        "usable_matches": usable,
        "coverage": (usable / total_matches) if total_matches else 0.0,
        "log_loss": (total_log_loss / usable) if usable else None,
        "brier": (total_brier / usable) if usable else None,
        "accuracy": (total_correct / usable) if usable else None,
        "mean_overround": (total_overround / usable) if usable else None,
        "brier_definition": "sum of squared errors across H/D/A probabilities; lower is better",
        "seasons": season_rows,
    }


def standard_report(db_path: Path) -> dict[str, object]:
    specifications = [
        ("B365", "pre_closing"),
        ("B365", "closing"),
        ("Avg", "pre_closing"),
        ("Avg", "closing"),
    ]
    return {
        "database": str(db_path),
        "baselines": [evaluate_market_baseline(db_path, source, phase) for source, phase in specifications],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score de-vigged bookmaker 1X2 probability baselines.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source", default=None)
    parser.add_argument("--phase", choices=("pre_closing", "closing"), default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if (args.source is None) != (args.phase is None):
        raise SystemExit("--source and --phase must be supplied together")

    report = (
        evaluate_market_baseline(args.database, args.source, args.phase)
        if args.source is not None
        else standard_report(args.database)
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote market baseline report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
