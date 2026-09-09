from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from football1.balanced_market_outcome_decomposition import _summary
from football1.draw_possibility_audit import FIXED_BALANCE_THRESHOLDS
from football1.features import build_feature_rows
from football1.market_baseline import devig_decimal_odds


RESULT_TO_OUTCOME = {"H": "home", "D": "draw", "A": "away"}
GROUPS = ("away_elo_stronger", "home_elo_at_least_as_strong")


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
    elo_diff = float(row.elo_diff)
    return {
        "season_start_year": int(row.season_start_year),
        "match_id": str(row.match_id),
        "result": result,
        "probability": {"home": float(probs[0]), "draw": float(probs[1]), "away": float(probs[2])},
        "odds": odds,
        "home_away_gap": abs(float(probs[0]) - float(probs[2])),
        "elo_diff": elo_diff,
        "strength_group": "away_elo_stronger" if elo_diff < 0.0 else "home_elo_at_least_as_strong",
    }


def _group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = _summary(rows)
    result["mean_raw_elo_diff_home_minus_away"] = (
        sum(float(row["elo_diff"]) for row in rows) / len(rows) if rows else None
    )
    return result


def _threshold_report(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    bucket = [row for row in rows if float(row["home_away_gap"]) <= threshold]
    groups = {
        group: [row for row in bucket if row["strength_group"] == group]
        for group in GROUPS
    }
    return {
        "max_home_away_gap": threshold,
        "matches": len(bucket),
        "away_elo_stronger_share": len(groups["away_elo_stronger"]) / len(bucket) if bucket else None,
        "overall": _group_summary(bucket),
        "groups": {group: _group_summary(group_rows) for group, group_rows in groups.items()},
    }


def _season_stability(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    seasons = sorted({int(row["season_start_year"]) for row in rows})
    reports: list[dict[str, Any]] = []
    for season in seasons:
        season_rows = [
            row for row in rows
            if int(row["season_start_year"]) == season and float(row["home_away_gap"]) <= threshold
        ]
        groups = {
            group: [row for row in season_rows if row["strength_group"] == group]
            for group in GROUPS
        }
        reports.append(
            {
                "season_start_year": season,
                "matches": len(season_rows),
                "groups": {group: _group_summary(group_rows) for group, group_rows in groups.items()},
            }
        )

    sign_counts: dict[str, Any] = {}
    for group in GROUPS:
        usable = [report for report in reports if int(report["groups"][group]["matches"]) > 0]
        sign_counts[group] = {
            "seasons_observed": len(usable),
            "positive_draw_residual_seasons": sum(
                1 for report in usable
                if float(report["groups"][group]["outcomes"]["draw"]["actual_minus_market"]) > 0.0
            ),
            "positive_draw_roi_seasons": sum(
                1 for report in usable
                if float(report["groups"][group]["outcomes"]["draw"]["flat_roi"]) > 0.0
            ),
            "negative_away_residual_seasons": sum(
                1 for report in usable
                if float(report["groups"][group]["outcomes"]["away"]["actual_minus_market"]) < 0.0
            ),
        }
    return {
        "max_home_away_gap": threshold,
        "sign_counts": sign_counts,
        "seasons": reports,
    }


def audit_balanced_venue_neutralization(db_path: Path) -> dict[str, Any]:
    rows = [x for raw in build_feature_rows(db_path) if (x := _row_from_feature(raw)) is not None]
    return {
        "experiment": "balanced_venue_neutralization_audit_v1",
        "status": "historical_post_hoc_zero_decision_weight",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "question": (
            "Is the balanced-match draw excess concentrated in fixtures where raw pre-match Elo rates the away team "
            "as intrinsically stronger, consistent with away strength being offset by home venue advantage?"
        ),
        "group_definition": {
            "elo_diff": "existing strictly pre-match raw Elo rating: home Elo minus away Elo; no venue bonus is included in this stored feature",
            "away_elo_stronger": "elo_diff < 0",
            "home_elo_at_least_as_strong": "elo_diff >= 0",
            "threshold_status": "sign split only; no Elo magnitude cutoff introduced",
        },
        "fixed_balance_thresholds": [
            _threshold_report(rows, threshold) for threshold in FIXED_BALANCE_THRESHOLDS
        ],
        "season_stability": [
            _season_stability(rows, threshold) for threshold in FIXED_BALANCE_THRESHOLDS
        ],
        "guardrails": [
            "This mechanism was proposed after observing the balanced-match draw anomaly and is post-hoc historical research.",
            "The same predeclared 2pp, 5pp and 10pp market-balance thresholds are retained without optimization.",
            "The Elo split uses sign only and introduces no fitted magnitude threshold.",
            "A concentration of draw residual in the away-Elo-strong subgroup would support a mechanism hypothesis, not establish causality.",
            "No probability, fair price, stake, confidence, recommendation or existing prospective shadow changes."
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit whether venue-neutralized away strength explains balanced EPL draw excess.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = audit_balanced_venue_neutralization(args.database)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote balanced venue neutralization audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
