from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from football1.draw_possibility_audit import FIXED_BALANCE_THRESHOLDS
from football1.features import build_feature_rows
from football1.market_baseline import devig_decimal_odds


def _row_from_feature(row: Any) -> dict[str, Any] | None:
    if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
        return None
    probs, _ = devig_decimal_odds(
        (float(row.b365_home), float(row.b365_draw), float(row.b365_away))
    )
    return {
        "season_start_year": int(row.season_start_year),
        "is_draw": str(row.result) == "D",
        "p_draw": float(probs[1]),
        "home_away_gap": abs(float(probs[0]) - float(probs[2])),
    }


def poisson_binomial_upper_tail(probabilities: list[float], observed: int) -> float:
    """Exact P(X >= observed) for independent Bernoulli trials with unequal p."""
    n = len(probabilities)
    if observed < 0 or observed > n:
        raise ValueError("observed must be between zero and number of probabilities")
    if any((not math.isfinite(p)) or p < 0.0 or p > 1.0 for p in probabilities):
        raise ValueError("probabilities must be finite and between zero and one")
    if observed == 0:
        return 1.0
    distribution = [0.0] * (n + 1)
    distribution[0] = 1.0
    used = 0
    for p in probabilities:
        used += 1
        for k in range(used, 0, -1):
            distribution[k] = distribution[k] * (1.0 - p) + distribution[k - 1] * p
        distribution[0] *= 1.0 - p
    return min(1.0, max(0.0, sum(distribution[observed:])))


def binomial_upper_tail(n: int, observed: int, p: float = 0.5) -> float:
    if n < 0 or observed < 0 or observed > n:
        raise ValueError("invalid binomial counts")
    if p < 0.0 or p > 1.0:
        raise ValueError("p must be between zero and one")
    return sum(
        math.comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k))
        for k in range(observed, n + 1)
    )


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for index, (key, p_value) in enumerate(ordered):
        candidate = min(1.0, (m - index) * p_value)
        running = max(running, candidate)
        adjusted[key] = running
    return adjusted


def _threshold_summary(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    bucket = [row for row in rows if float(row["home_away_gap"]) <= threshold]
    probabilities = [float(row["p_draw"]) for row in bucket]
    observed = sum(int(row["is_draw"]) for row in bucket)
    n = len(bucket)
    expected = sum(probabilities)
    variance = sum(p * (1.0 - p) for p in probabilities)
    sd = math.sqrt(variance)
    residual_draws = observed - expected
    residual_rate = residual_draws / n if n else None
    se_rate = sd / n if n else None

    seasons = sorted({int(row["season_start_year"]) for row in bucket})
    season_rows = []
    for season in seasons:
        part = [row for row in bucket if int(row["season_start_year"]) == season]
        season_observed = sum(int(row["is_draw"]) for row in part)
        season_expected = sum(float(row["p_draw"]) for row in part)
        season_rows.append(
            {
                "season_start_year": season,
                "matches": len(part),
                "observed_draws": season_observed,
                "expected_draws_from_market": season_expected,
                "residual_draws": season_observed - season_expected,
                "positive_residual": season_observed > season_expected,
            }
        )
    positive_seasons = sum(int(row["positive_residual"]) for row in season_rows)

    return {
        "max_home_away_gap": threshold,
        "matches": n,
        "observed_draws": observed,
        "expected_draws_from_individual_market_pdraw": expected,
        "residual_draws": residual_draws,
        "observed_draw_rate": observed / n if n else None,
        "mean_market_draw_probability": expected / n if n else None,
        "draw_rate_residual": residual_rate,
        "independence_standard_error_of_residual_rate": se_rate,
        "independence_95pct_normal_interval_for_residual_rate": (
            [residual_rate - 1.96 * se_rate, residual_rate + 1.96 * se_rate]
            if residual_rate is not None and se_rate is not None
            else None
        ),
        "poisson_binomial_one_sided_p": poisson_binomial_upper_tail(probabilities, observed) if n else None,
        "season_sign_robustness": {
            "seasons": len(season_rows),
            "positive_residual_seasons": positive_seasons,
            "one_sided_binomial_sign_p": (
                binomial_upper_tail(len(season_rows), positive_seasons, 0.5) if season_rows else None
            ),
            "season_rows": season_rows,
        },
    }


def audit_draw_balance_uncertainty(db_path: Path) -> dict[str, Any]:
    rows = [x for raw in build_feature_rows(db_path) if (x := _row_from_feature(raw)) is not None]
    reports = [_threshold_summary(rows, threshold) for threshold in FIXED_BALANCE_THRESHOLDS]
    raw_p = {
        f"{int(round(report['max_home_away_gap'] * 100))}pp": float(report["poisson_binomial_one_sided_p"])
        for report in reports
    }
    adjusted = holm_adjust(raw_p)
    for report in reports:
        key = f"{int(round(report['max_home_away_gap'] * 100))}pp"
        report["holm_adjusted_one_sided_p_across_three_nested_probes"] = adjusted[key]

    return {
        "experiment": "draw_balance_uncertainty_audit_v1",
        "status": "historical_post_hoc_zero_decision_weight",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "question": (
            "How surprising is the observed excess number of draws in the fixed 2pp/5pp/10pp balanced-market groups "
            "under each match's own bookmaker draw probability?"
        ),
        "method": {
            "primary": "exact Poisson-binomial upper-tail probability using individual de-vigged B365 pDraw values",
            "multiple_probe_adjustment": "Holm adjustment across the three already-fixed nested balance probes",
            "secondary": "season-level sign test of positive observed-minus-expected draw residual",
            "important_limitation": (
                "The Poisson-binomial calculation treats match outcomes as independent conditional on market probabilities. "
                "Football seasons, teams and regimes create dependence, so the season-sign diagnostic is retained as a coarser robustness check."
            ),
        },
        "fixed_balance_thresholds": reports,
        "guardrails": [
            "This uncertainty audit follows discovery of the historical balance clue and cannot turn it into untouched validation.",
            "A small unadjusted tail probability is not a betting rule and must be considered with the multiple-probe and season-stability results.",
            "No probability, fair price, threshold, stake, confidence or prospective ranking is changed.",
            "The frozen 12-14 September prospective Draw Possibility test remains the clean evidence path."
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quantify uncertainty around the historical balanced-match Draw excess.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = audit_draw_balance_uncertainty(args.database)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote draw balance uncertainty audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
