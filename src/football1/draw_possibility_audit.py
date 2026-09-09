from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from sklearn.metrics import roc_auc_score

from football1.features import build_feature_rows
from football1.market_baseline import devig_decimal_odds


GAP_BINS = (
    ("0-2pp", 0.00, 0.02),
    ("2-5pp", 0.02, 0.05),
    ("5-10pp", 0.05, 0.10),
    ("10-15pp", 0.10, 0.15),
    ("15pp+", 0.15, math.inf),
)
FAV_BINS = (
    ("<40%", 0.00, 0.40),
    ("40-45%", 0.40, 0.45),
    ("45-50%", 0.45, 0.50),
    ("50-60%", 0.50, 0.60),
    ("60%+", 0.60, 1.01),
)
FIXED_BALANCE_THRESHOLDS = (0.02, 0.05, 0.10)


def _market_row(row: Any) -> dict[str, Any] | None:
    if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
        return None
    odds = (float(row.b365_home), float(row.b365_draw), float(row.b365_away))
    probs, _ = devig_decimal_odds(odds)
    p_home, p_draw, p_away = probs
    return {
        "season_start_year": int(row.season_start_year),
        "match_id": str(row.match_id),
        "match_date": str(row.match_date),
        "home_team": str(row.home_team),
        "away_team": str(row.away_team),
        "result": str(row.result),
        "is_draw": str(row.result) == "D",
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
        "home_away_gap": abs(p_home - p_away),
        "favorite_probability": max(p_home, p_away),
        "draw_odds": float(row.b365_draw),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "matches": 0,
            "draws": 0,
            "draw_rate": None,
            "mean_market_draw_probability": None,
            "draw_rate_minus_market": None,
            "mean_draw_odds": None,
            "flat_draw_pnl_units": None,
            "flat_draw_roi": None,
        }
    n = len(rows)
    draws = sum(int(r["is_draw"]) for r in rows)
    mean_market = sum(float(r["p_draw"]) for r in rows) / n
    pnl = sum((float(r["draw_odds"]) - 1.0) if r["is_draw"] else -1.0 for r in rows)
    return {
        "matches": n,
        "draws": draws,
        "draw_rate": draws / n,
        "mean_market_draw_probability": mean_market,
        "draw_rate_minus_market": draws / n - mean_market,
        "mean_draw_odds": sum(float(r["draw_odds"]) for r in rows) / n,
        "flat_draw_pnl_units": pnl,
        "flat_draw_roi": pnl / n,
    }


def _fixed_bins(rows: list[dict[str, Any]], bins: tuple[tuple[str, float, float], ...], field: str) -> list[dict[str, Any]]:
    result = []
    for label, lo, hi in bins:
        bucket = [r for r in rows if lo <= float(r[field]) < hi]
        result.append({"label": label, "lower": lo, "upper": None if math.isinf(hi) else hi, **_summary(bucket)})
    return result


def _season_trend(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seasons = sorted({int(r["season_start_year"]) for r in rows})
    return [
        {"season_start_year": season, **_summary([r for r in rows if int(r["season_start_year"]) == season])}
        for season in seasons
    ]


def _linear_draw_rate_slope(season_rows: list[dict[str, Any]]) -> float | None:
    usable = [r for r in season_rows if r["draw_rate"] is not None]
    if len(usable) < 2:
        return None
    xs = [float(r["season_start_year"]) for r in usable]
    ys = [float(r["draw_rate"]) for r in usable]
    xm = sum(xs) / len(xs)
    ym = sum(ys) / len(ys)
    denom = sum((x - xm) ** 2 for x in xs)
    return sum((x - xm) * (y - ym) for x, y in zip(xs, ys, strict=True)) / denom if denom else None


def _closeness_auc(rows: list[dict[str, Any]]) -> float | None:
    positives = sum(int(r["is_draw"]) for r in rows)
    if positives == 0 or positives == len(rows):
        return None
    return float(
        roc_auc_score(
            [int(r["is_draw"]) for r in rows],
            [-float(r["home_away_gap"]) for r in rows],
        )
    )


def _market_draw_auc(rows: list[dict[str, Any]]) -> float | None:
    positives = sum(int(r["is_draw"]) for r in rows)
    if positives == 0 or positives == len(rows):
        return None
    return float(roc_auc_score([int(r["is_draw"]) for r in rows], [float(r["p_draw"]) for r in rows]))


def audit_draw_possibility(db_path: Path) -> dict[str, Any]:
    rows = [x for row in build_feature_rows(db_path) if (x := _market_row(row)) is not None]
    overall = _summary(rows)
    season_rows = _season_trend(rows)

    thresholds = []
    for threshold in FIXED_BALANCE_THRESHOLDS:
        bucket = [r for r in rows if float(r["home_away_gap"]) <= threshold]
        thresholds.append(
            {
                "max_home_away_gap": threshold,
                "description": f"de-vigged market home/away probabilities within {threshold * 100:.0f} percentage points",
                **_summary(bucket),
                "draw_rate_lift_vs_all": (
                    float(_summary(bucket)["draw_rate"]) / float(overall["draw_rate"])
                    if bucket and overall["draw_rate"]
                    else None
                ),
            }
        )

    ranked = sorted(rows, key=lambda r: (float(r["home_away_gap"]), -float(r["p_draw"])))
    top_count = max(1, math.ceil(len(ranked) * 0.20)) if ranked else 0
    closest_quintile = ranked[:top_count]

    return {
        "experiment": "draw_possibility_market_balance_audit_v1",
        "status": "historical_descriptive_zero_decision_weight",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "definition": {
            "probability": "ordinary H/D/A probability used for fair pricing",
            "possibility": (
                "relative draw-likeness based on match shape; here the simplest shape is how close the de-vigged market home and away probabilities are. "
                "It is a ranking/conditioning lens, not a fourth probability and does not need to sum to one."
            ),
            "core_score": "smaller absolute gap between market home and away probabilities means higher draw possibility",
        },
        "overall": overall,
        "season_draw_rates": season_rows,
        "linear_draw_rate_slope_per_season": _linear_draw_rate_slope(season_rows),
        "home_away_gap_bins": _fixed_bins(rows, GAP_BINS, "home_away_gap"),
        "favorite_probability_bins": _fixed_bins(rows, FAV_BINS, "favorite_probability"),
        "fixed_balance_thresholds": thresholds,
        "ranking_diagnostics": {
            "closeness_auc_for_draw": _closeness_auc(rows),
            "market_draw_probability_auc_for_draw": _market_draw_auc(rows),
            "closest_20pct": _summary(closest_quintile),
            "closest_20pct_draw_rate_lift_vs_all": (
                float(_summary(closest_quintile)["draw_rate"]) / float(overall["draw_rate"])
                if closest_quintile and overall["draw_rate"]
                else None
            ),
        },
        "guardrails": [
            "No draw probability is boosted or pasted onto the existing model.",
            "The fixed 2/5/10pp balance thresholds are sensitivity probes, not validated betting cutoffs.",
            "Flat draw ROI is descriptive and uses historical B365 pre-closing quotes; it is not a prospective recommendation.",
            "If balanced-match draw frequency does not exceed the market draw probability, closeness may make draws visible without creating price edge.",
            "Any future individual Draw Possibility score must be frozen and tested prospectively before decision weight is allowed.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit simple market-balance draw possibility without altering H/D/A probabilities.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = audit_draw_possibility(args.database)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote draw possibility audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
