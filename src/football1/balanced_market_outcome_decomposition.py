from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from football1.draw_possibility_audit import FIXED_BALANCE_THRESHOLDS, GAP_BINS
from football1.features import build_feature_rows
from football1.market_baseline import devig_decimal_odds


OUTCOMES = ("home", "draw", "away")
RESULT_TO_OUTCOME = {"H": "home", "D": "draw", "A": "away"}


def _row_from_feature(row: Any) -> dict[str, Any] | None:
    if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
        return None
    odds = {
        "home": float(row.b365_home),
        "draw": float(row.b365_draw),
        "away": float(row.b365_away),
    }
    probs, _ = devig_decimal_odds((odds["home"], odds["draw"], odds["away"]))
    result = RESULT_TO_OUTCOME.get(str(row.result))
    if result is None:
        return None
    return {
        "season_start_year": int(row.season_start_year),
        "match_id": str(row.match_id),
        "result": result,
        "probability": {"home": float(probs[0]), "draw": float(probs[1]), "away": float(probs[2])},
        "odds": odds,
        "home_away_gap": abs(float(probs[0]) - float(probs[2])),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "matches": 0,
            "outcomes": {
                outcome: {
                    "wins": 0,
                    "actual_frequency": None,
                    "mean_market_probability": None,
                    "actual_minus_market": None,
                    "mean_odds": None,
                    "flat_pnl_units": None,
                    "flat_roi": None,
                }
                for outcome in OUTCOMES
            },
        }
    n = len(rows)
    outcomes: dict[str, Any] = {}
    for outcome in OUTCOMES:
        wins = sum(int(row["result"] == outcome) for row in rows)
        actual = wins / n
        mean_market = sum(float(row["probability"][outcome]) for row in rows) / n
        pnl = sum(
            (float(row["odds"][outcome]) - 1.0) if row["result"] == outcome else -1.0
            for row in rows
        )
        outcomes[outcome] = {
            "wins": wins,
            "actual_frequency": actual,
            "mean_market_probability": mean_market,
            "actual_minus_market": actual - mean_market,
            "mean_odds": sum(float(row["odds"][outcome]) for row in rows) / n,
            "flat_pnl_units": pnl,
            "flat_roi": pnl / n,
        }
    return {"matches": n, "outcomes": outcomes}


def _disjoint_bins(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for label, lo, hi in GAP_BINS:
        bucket = [row for row in rows if lo <= float(row["home_away_gap"]) < hi]
        result.append(
            {
                "label": label,
                "lower": lo,
                "upper": None if math.isinf(hi) else hi,
                **_summary(bucket),
            }
        )
    return result


def _season_stability(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    seasons = sorted({int(row["season_start_year"]) for row in rows})
    reports = []
    for season in seasons:
        bucket = [
            row for row in rows
            if int(row["season_start_year"]) == season and float(row["home_away_gap"]) <= threshold
        ]
        report = {"season_start_year": season, **_summary(bucket)}
        reports.append(report)

    nonempty = [report for report in reports if int(report["matches"]) > 0]
    sign_counts = {
        outcome: {
            "positive_probability_residual_seasons": sum(
                1
                for report in nonempty
                if float(report["outcomes"][outcome]["actual_minus_market"]) > 0.0
            ),
            "negative_probability_residual_seasons": sum(
                1
                for report in nonempty
                if float(report["outcomes"][outcome]["actual_minus_market"]) < 0.0
            ),
            "positive_flat_roi_seasons": sum(
                1
                for report in nonempty
                if float(report["outcomes"][outcome]["flat_roi"]) > 0.0
            ),
        }
        for outcome in OUTCOMES
    }
    return {
        "max_home_away_gap": threshold,
        "seasons_observed": len(nonempty),
        "sign_counts": sign_counts,
        "seasons": reports,
    }


def audit_balanced_market_outcomes(db_path: Path) -> dict[str, Any]:
    rows = [x for raw in build_feature_rows(db_path) if (x := _row_from_feature(raw)) is not None]
    thresholds = []
    for threshold in FIXED_BALANCE_THRESHOLDS:
        bucket = [row for row in rows if float(row["home_away_gap"]) <= threshold]
        thresholds.append(
            {
                "max_home_away_gap": threshold,
                "description": f"de-vigged market home/away probabilities within {threshold * 100:.0f} percentage points",
                **_summary(bucket),
            }
        )

    return {
        "experiment": "balanced_market_outcome_decomposition_v1",
        "status": "historical_post_hoc_zero_decision_weight",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "question": (
            "When balanced H/A market shapes show excess realized draws, which H/D/A outcomes "
            "are over- or under-allocated probability by the market?"
        ),
        "overall": _summary(rows),
        "fixed_balance_thresholds": thresholds,
        "disjoint_gap_bins": _disjoint_bins(rows),
        "season_stability": [
            _season_stability(rows, threshold) for threshold in FIXED_BALANCE_THRESHOLDS
        ],
        "guardrails": [
            "This decomposition follows inspection of the historical Draw Possibility clue and is post-hoc.",
            "The original 2pp, 5pp and 10pp thresholds are retained without optimization.",
            "Flat ROI uses historical B365 pre-closing odds and is descriptive, not a recommendation.",
            "No H/D/A probability, fair price, stake, confidence or product decision is changed.",
            "The prospective Draw Possibility shadow remains the required confirmation path."
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decompose H/D/A market residuals in balanced EPL matches.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = audit_balanced_market_outcomes(args.database)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote balanced market outcome decomposition to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
