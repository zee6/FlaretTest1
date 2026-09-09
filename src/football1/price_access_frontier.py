from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

from football1.price_shopping_audit import EXCHANGE_KEYS, OUTCOMES, _finite_price, _quantile, _read_jsonl


DECISION_WEIGHT = 0.0


def build_price_matrix(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for record in records:
        if record.get("status") != "pre_kickoff_odds_snapshot":
            continue
        for outcome in OUTCOMES:
            quotes: dict[str, dict[str, Any]] = {}
            for bookmaker in record.get("bookmakers", []):
                if not isinstance(bookmaker, dict):
                    continue
                key = str(bookmaker.get("bookmaker_key") or "")
                if not key or key in EXCHANGE_KEYS:
                    continue
                decimal = bookmaker.get("decimal_odds")
                if not isinstance(decimal, dict):
                    continue
                price = _finite_price(decimal.get(outcome))
                if price is None:
                    continue
                quotes[key] = {
                    "bookmaker_title": str(bookmaker.get("bookmaker_title") or key),
                    "price": price,
                }
            if not quotes:
                continue
            full_best = max(float(value["price"]) for value in quotes.values())
            observations.append(
                {
                    "observation_id": f"{record.get('record_id')}:{outcome}",
                    "record_id": record.get("record_id"),
                    "event_id": record.get("event_id"),
                    "retrieved_at_utc": record.get("retrieved_at_utc"),
                    "home_team": record.get("home_team"),
                    "away_team": record.get("away_team"),
                    "outcome": outcome,
                    "full_best_price": full_best,
                    "quotes": quotes,
                }
            )
    observations.sort(key=lambda row: (str(row["retrieved_at_utc"]), str(row["event_id"]), str(row["outcome"])))
    return observations


def evaluate_book_set(observations: list[dict[str, Any]], bookmaker_keys: list[str]) -> dict[str, Any]:
    if not observations:
        return {
            "bookmakers": list(bookmaker_keys),
            "observations": 0,
            "served_fraction": None,
            "exact_best_fraction": None,
            "within_1pct_of_best_fraction": None,
            "within_2pct_of_best_fraction": None,
            "mean_price_shortfall_vs_full_best": None,
            "median_price_shortfall_vs_full_best": None,
            "p90_price_shortfall_vs_full_best": None,
            "mean_profit_shortfall_vs_full_best_if_win": None,
        }

    selected = set(bookmaker_keys)
    shortfalls: list[float] = []
    profit_shortfalls: list[float] = []
    exact = 0
    within_1 = 0
    within_2 = 0
    served = 0

    for row in observations:
        available = [
            float(quote["price"])
            for key, quote in row["quotes"].items()
            if key in selected
        ]
        if not available:
            continue
        served += 1
        achieved = max(available)
        full_best = float(row["full_best_price"])
        shortfall = max(0.0, 1.0 - achieved / full_best)
        shortfalls.append(shortfall)
        profit_shortfall = max(0.0, (full_best - achieved) / (full_best - 1.0))
        profit_shortfalls.append(profit_shortfall)
        if math.isclose(achieved, full_best, abs_tol=1e-12):
            exact += 1
        if shortfall <= 0.01 + 1e-12:
            within_1 += 1
        if shortfall <= 0.02 + 1e-12:
            within_2 += 1

    denominator = len(observations)
    return {
        "bookmakers": list(bookmaker_keys),
        "observations": denominator,
        "served_fraction": served / denominator,
        "exact_best_fraction": exact / denominator,
        "within_1pct_of_best_fraction": within_1 / denominator,
        "within_2pct_of_best_fraction": within_2 / denominator,
        "mean_price_shortfall_vs_full_best": statistics.fmean(shortfalls) if shortfalls else None,
        "median_price_shortfall_vs_full_best": statistics.median(shortfalls) if shortfalls else None,
        "p90_price_shortfall_vs_full_best": _quantile(shortfalls, 0.90),
        "mean_profit_shortfall_vs_full_best_if_win": statistics.fmean(profit_shortfalls) if profit_shortfalls else None,
    }


def greedy_price_frontier(observations: list[dict[str, Any]]) -> dict[str, Any]:
    all_keys = sorted({key for row in observations for key in row["quotes"]})
    titles = {
        key: str(quote.get("bookmaker_title") or key)
        for row in observations
        for key, quote in row["quotes"].items()
    }
    selected: list[str] = []
    remaining = set(all_keys)
    frontier: list[dict[str, Any]] = []

    while remaining:
        best_key = None
        best_score = None
        best_eval = None
        for key in sorted(remaining):
            trial = selected + [key]
            metrics = evaluate_book_set(observations, trial)
            mean_shortfall = metrics["mean_price_shortfall_vs_full_best"]
            served = float(metrics["served_fraction"] or 0.0)
            shortfall_score = 1.0 - float(mean_shortfall) if mean_shortfall is not None else 0.0
            # Coverage dominates: an account set that has no quote for an
            # observation should not look superior merely because it is close
            # to best on the smaller served subset.
            score = served * shortfall_score
            tie_break = float(metrics["exact_best_fraction"] or 0.0)
            candidate_score = (score, tie_break, key)
            if best_score is None or candidate_score > best_score:
                best_score = candidate_score
                best_key = key
                best_eval = metrics
        if best_key is None or best_eval is None:
            break
        selected.append(best_key)
        remaining.remove(best_key)
        frontier.append(
            {
                "account_count": len(selected),
                "added_bookmaker_key": best_key,
                "added_bookmaker_title": titles.get(best_key, best_key),
                **best_eval,
            }
        )

    return {
        "sportsbooks_available": len(all_keys),
        "observations": len(observations),
        "selection_method": (
            "Greedy post-hoc set chosen to maximize served fraction times closeness to the full best price; ties prefer exact-best coverage."
        ),
        "frontier": frontier,
        "warning": (
            "This frontier is descriptive on the already observed quote archive. It does not identify a stable bookmaker portfolio for future use."
        ),
    }


def price_access_frontier(archive_path: Path) -> dict[str, Any]:
    records = _read_jsonl(archive_path)
    observations = build_price_matrix(records)
    return {
        "experiment": "prospective_best_price_access_frontier_v1",
        "status": "prospective_price_structure_observer_zero_weight",
        "decision_weight": DECISION_WEIGHT,
        "promotion_allowed": False,
        "portfolio_currency": "GBP",
        "exchange_keys_excluded": sorted(EXCHANGE_KEYS),
        "frontier": greedy_price_frontier(observations),
        "governance": {
            "bookmaker_set_is_product_recommendation": False,
            "affiliate_status_affects_selection": False,
            "probability_model_changed": False,
            "stake_rule_changed": False,
        },
        "warning": (
            "The account-access frontier measures practical price loss in a small prospective quote archive. It does not account for limits, eligibility, account restrictions or future bookmaker behaviour."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Measure the practical EPL best-price frontier as sportsbook-account access increases.")
    parser.add_argument("--archive", type=Path, default=Path("prospective/odds_snapshots.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/price_access_frontier.json"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = price_access_frontier(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = report["frontier"]["frontier"]
    compact = [
        {
            "accounts": row["account_count"],
            "added": row["added_bookmaker_title"],
            "served": row["served_fraction"],
            "exact_best": row["exact_best_fraction"],
            "within_1pct": row["within_1pct_of_best_fraction"],
            "mean_shortfall": row["mean_price_shortfall_vs_full_best"],
        }
        for row in rows
    ]
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
