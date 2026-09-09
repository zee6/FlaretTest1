from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


OUTCOMES = ("home", "draw", "away")
# Exchange back prices are kept visible but excluded from the default directly
# comparable sportsbook best-price calculation because exchange commission can
# depend on venue/account terms and is not encoded in the Odds API quote.
EXCHANGE_KEYS = frozenset({"betfair_ex_uk", "matchbook", "smarkets"})
DECISION_WEIGHT = 0.0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on {path} line {line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Expected object on {path} line {line_number}")
        rows.append(row)
    return rows


def _finite_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 1.0:
        return None
    return price


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _is_exchange(quote: dict[str, Any]) -> bool:
    return str(quote.get("bookmaker_key") or "") in EXCHANGE_KEYS


def _quotes_for_outcome(record: dict[str, Any], outcome: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if outcome not in OUTCOMES:
        raise ValueError(f"Unknown outcome: {outcome}")
    sportsbook: list[dict[str, Any]] = []
    exchanges: list[dict[str, Any]] = []
    for quote in record.get("bookmakers", []):
        if not isinstance(quote, dict):
            continue
        decimal = quote.get("decimal_odds")
        if not isinstance(decimal, dict):
            continue
        price = _finite_price(decimal.get(outcome))
        if price is None:
            continue
        normalized = {
            "bookmaker_key": str(quote.get("bookmaker_key") or ""),
            "bookmaker_title": str(quote.get("bookmaker_title") or quote.get("bookmaker_key") or "unknown"),
            "last_update_utc": quote.get("last_update_utc"),
            "price": price,
        }
        (exchanges if _is_exchange(quote) else sportsbook).append(normalized)
    sportsbook.sort(key=lambda q: (-float(q["price"]), str(q["bookmaker_key"])))
    exchanges.sort(key=lambda q: (-float(q["price"]), str(q["bookmaker_key"])))
    return sportsbook, exchanges


def _best_ties(quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not quotes:
        return []
    best = max(float(q["price"]) for q in quotes)
    return [q for q in quotes if math.isclose(float(q["price"]), best, abs_tol=1e-12)]


def quote_observation(record: dict[str, Any], outcome: str) -> dict[str, Any] | None:
    sportsbook, exchanges = _quotes_for_outcome(record, outcome)
    if not sportsbook:
        return None

    prices = [float(q["price"]) for q in sportsbook]
    best_price = max(prices)
    median_price = float(statistics.median(prices))
    mean_price = float(statistics.fmean(prices))
    worst_price = min(prices)
    best_books = _best_ties(sportsbook)
    exchange_best = max((float(q["price"]) for q in exchanges), default=None)
    exchange_best_books = _best_ties(exchanges)

    consensus_raw = record.get("consensus_fair_probability")
    consensus_probability = None
    if isinstance(consensus_raw, dict):
        try:
            candidate = float(consensus_raw[outcome])
        except (KeyError, TypeError, ValueError):
            candidate = math.nan
        if math.isfinite(candidate) and 0.0 < candidate < 1.0:
            consensus_probability = candidate

    observation = {
        "observation_id": f"{record.get('record_id')}:{outcome}",
        "record_id": record.get("record_id"),
        "event_id": record.get("event_id"),
        "retrieved_at_utc": record.get("retrieved_at_utc"),
        "commence_time_utc": record.get("commence_time_utc"),
        "home_team": record.get("home_team"),
        "away_team": record.get("away_team"),
        "outcome": outcome,
        "sportsbook_count": len(sportsbook),
        "exchange_count": len(exchanges),
        "best_sportsbook_price": best_price,
        "best_sportsbook_books": [
            {
                "bookmaker_key": q["bookmaker_key"],
                "bookmaker_title": q["bookmaker_title"],
                "last_update_utc": q["last_update_utc"],
            }
            for q in best_books
        ],
        "median_sportsbook_price": median_price,
        "mean_sportsbook_price": mean_price,
        "worst_sportsbook_price": worst_price,
        "gross_return_uplift_best_vs_median": best_price / median_price - 1.0,
        "gross_return_uplift_best_vs_mean": best_price / mean_price - 1.0,
        "gross_return_uplift_best_vs_worst": best_price / worst_price - 1.0,
        "break_even_probability_reduction_best_vs_median": 1.0 / median_price - 1.0 / best_price,
        "consensus_probability": consensus_probability,
        "consensus_fair_odds": 1.0 / consensus_probability if consensus_probability else None,
        "consensus_ev_at_best_sportsbook": consensus_probability * best_price - 1.0 if consensus_probability else None,
        "consensus_ev_at_median_sportsbook": consensus_probability * median_price - 1.0 if consensus_probability else None,
        "consensus_ev_improvement_from_shopping": (
            consensus_probability * (best_price - median_price) if consensus_probability else None
        ),
        "best_raw_exchange_price": exchange_best,
        "best_raw_exchange_books": [
            {
                "bookmaker_key": q["bookmaker_key"],
                "bookmaker_title": q["bookmaker_title"],
                "last_update_utc": q["last_update_utc"],
            }
            for q in exchange_best_books
        ],
        "raw_exchange_beats_sportsbook": exchange_best is not None and exchange_best > best_price,
    }
    return observation


def build_quote_observations(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for record in records:
        if record.get("status") != "pre_kickoff_odds_snapshot":
            continue
        for outcome in OUTCOMES:
            observation = quote_observation(record, outcome)
            if observation is not None:
                observations.append(observation)
    observations.sort(
        key=lambda row: (str(row["retrieved_at_utc"]), str(row["event_id"]), OUTCOMES.index(str(row["outcome"])))
    )
    return observations


def greedy_best_price_coverage(observations: list[dict[str, Any]]) -> dict[str, Any]:
    universe = {str(row["observation_id"]) for row in observations}
    by_book: dict[str, set[str]] = defaultdict(set)
    titles: dict[str, str] = {}
    for row in observations:
        observation_id = str(row["observation_id"])
        for book in row.get("best_sportsbook_books", []):
            key = str(book.get("bookmaker_key") or "")
            if not key:
                continue
            by_book[key].add(observation_id)
            titles[key] = str(book.get("bookmaker_title") or key)

    uncovered = set(universe)
    picks: list[dict[str, Any]] = []
    while uncovered:
        candidates = [
            (len(hits & uncovered), key, hits)
            for key, hits in by_book.items()
            if hits & uncovered
        ]
        if not candidates:
            break
        hit_count, key, hits = max(candidates, key=lambda item: (item[0], item[1]))
        newly = hits & uncovered
        uncovered -= newly
        picks.append(
            {
                "rank": len(picks) + 1,
                "bookmaker_key": key,
                "bookmaker_title": titles.get(key, key),
                "new_best_price_observations_covered": hit_count,
                "cumulative_best_price_observations_covered": len(universe) - len(uncovered),
                "cumulative_fraction": (len(universe) - len(uncovered)) / len(universe) if universe else None,
            }
        )

    def books_needed(target: float) -> int | None:
        for pick in picks:
            if float(pick["cumulative_fraction"]) >= target:
                return int(pick["rank"])
        return None

    return {
        "observations": len(universe),
        "greedy_order": picks,
        "books_needed_for_50pct": books_needed(0.50),
        "books_needed_for_75pct": books_needed(0.75),
        "books_needed_for_90pct": books_needed(0.90),
        "books_needed_for_95pct": books_needed(0.95),
        "books_needed_for_100pct": books_needed(1.00),
        "warning": (
            "This is greedy snapshot coverage, not proof of a stable optimal account set. Tied best prices count as available at each tied sportsbook."
        ),
    }


def summarize_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    if not observations:
        return {
            "outcome_quote_observations": 0,
            "event_snapshots": 0,
            "price_uplift": {},
            "raw_exchange_comparison": {},
            "best_price_coverage": greedy_best_price_coverage([]),
        }

    uplift_median = [float(row["gross_return_uplift_best_vs_median"]) for row in observations]
    uplift_mean = [float(row["gross_return_uplift_best_vs_mean"]) for row in observations]
    uplift_worst = [float(row["gross_return_uplift_best_vs_worst"]) for row in observations]
    break_even = [float(row["break_even_probability_reduction_best_vs_median"]) for row in observations]
    consensus_improvements = [
        float(row["consensus_ev_improvement_from_shopping"])
        for row in observations
        if row.get("consensus_ev_improvement_from_shopping") is not None
    ]

    by_outcome: dict[str, Any] = {}
    for outcome in OUTCOMES:
        subset = [row for row in observations if row["outcome"] == outcome]
        values = [float(row["gross_return_uplift_best_vs_median"]) for row in subset]
        by_outcome[outcome] = {
            "observations": len(subset),
            "mean_best_vs_median_gross_return_uplift": statistics.fmean(values) if values else None,
            "median_best_vs_median_gross_return_uplift": statistics.median(values) if values else None,
            "p90_best_vs_median_gross_return_uplift": _quantile(values, 0.90),
        }

    book_best_counts: dict[str, dict[str, Any]] = {}
    for row in observations:
        for book in row.get("best_sportsbook_books", []):
            key = str(book.get("bookmaker_key") or "")
            if not key:
                continue
            block = book_best_counts.setdefault(
                key,
                {"bookmaker_title": str(book.get("bookmaker_title") or key), "tied_best_observations": 0},
            )
            block["tied_best_observations"] += 1

    ranked_books = sorted(
        (
            {"bookmaker_key": key, **value}
            for key, value in book_best_counts.items()
        ),
        key=lambda row: (-int(row["tied_best_observations"]), str(row["bookmaker_key"])),
    )

    return {
        "outcome_quote_observations": len(observations),
        "event_snapshots": len({str(row["record_id"]) for row in observations}),
        "sportsbook_count_per_observation": {
            "min": min(int(row["sportsbook_count"]) for row in observations),
            "median": statistics.median(int(row["sportsbook_count"]) for row in observations),
            "max": max(int(row["sportsbook_count"]) for row in observations),
        },
        "price_uplift": {
            "mean_best_vs_median_gross_return_uplift": statistics.fmean(uplift_median),
            "median_best_vs_median_gross_return_uplift": statistics.median(uplift_median),
            "p90_best_vs_median_gross_return_uplift": _quantile(uplift_median, 0.90),
            "mean_best_vs_mean_gross_return_uplift": statistics.fmean(uplift_mean),
            "mean_best_vs_worst_gross_return_uplift": statistics.fmean(uplift_worst),
            "mean_break_even_probability_reduction_best_vs_median": statistics.fmean(break_even),
            "mean_consensus_ev_improvement_best_vs_median": (
                statistics.fmean(consensus_improvements) if consensus_improvements else None
            ),
            "share_best_at_least_1pct_above_median": sum(v >= 0.01 for v in uplift_median) / len(uplift_median),
            "share_best_at_least_2pct_above_median": sum(v >= 0.02 for v in uplift_median) / len(uplift_median),
            "share_best_at_least_5pct_above_median": sum(v >= 0.05 for v in uplift_median) / len(uplift_median),
            "by_outcome": by_outcome,
        },
        "raw_exchange_comparison": {
            "observations_with_exchange_quote": sum(row.get("best_raw_exchange_price") is not None for row in observations),
            "raw_exchange_beats_best_sportsbook": sum(bool(row["raw_exchange_beats_sportsbook"]) for row in observations),
            "warning": (
                "Raw exchange prices are not commission-adjusted and are therefore not used as the default best-price benchmark."
            ),
        },
        "best_sportsbook_frequency": ranked_books,
        "best_price_coverage": greedy_best_price_coverage(observations),
    }


def locked_snapshot_join_diagnostic(
    archive_records: list[dict[str, Any]],
    ledger_records: list[dict[str, Any]],
) -> dict[str, Any]:
    available = {
        (str(row.get("event_id") or ""), str(row.get("retrieved_at_utc") or ""))
        for row in archive_records
        if row.get("status") == "pre_kickoff_odds_snapshot"
    }
    locks = [row for row in ledger_records if row.get("status") == "prediction_locked"]
    exact = [
        row
        for row in locks
        if (str(row.get("event_id") or ""), str(row.get("snapshot_retrieved_at_utc") or "")) in available
    ]
    return {
        "prediction_locks": len(locks),
        "exact_quote_board_matches": len(exact),
        "can_attribute_best_price_effect_to_locked_model_without_timing_mix": bool(exact),
        "warning": (
            "Model-EV attribution requires the full quote board from the exact prediction-lock timestamp. Later quote boards can measure price dispersion but must not be silently combined with earlier model probabilities."
        ),
    }


def price_shopping_audit(archive_path: Path, ledger_path: Path) -> dict[str, Any]:
    archive_records = _read_jsonl(archive_path)
    ledger_records = _read_jsonl(ledger_path)
    observations = build_quote_observations(archive_records)
    return {
        "experiment": "prospective_best_price_economics_v1",
        "status": "prospective_price_structure_observer_zero_weight",
        "decision_weight": DECISION_WEIGHT,
        "promotion_allowed": False,
        "portfolio_currency": "GBP",
        "competition": "English Premier League",
        "default_best_price_universe": "complete UK sportsbook H/D/A triplets in the observed snapshot; known exchanges excluded",
        "exchange_keys_excluded_from_default": sorted(EXCHANGE_KEYS),
        "quote_economics": summarize_observations(observations),
        "locked_snapshot_join": locked_snapshot_join_diagnostic(archive_records, ledger_records),
        "records": observations,
        "governance": {
            "best_price_changes_probability": False,
            "best_price_changes_payout_and_break_even": True,
            "affiliate_status_affects_sorting": False,
            "exchange_commission_assumed": None,
            "settled_result_required_for_price_uplift_measurement": False,
            "historical_b365_backtest_rewritten_with_best_prices": False,
        },
        "warning": (
            "Price shopping can improve the economics of a fixed selection but cannot create predictive edge. "
            "The archive is a small prospective quote sample, not a historical multi-book backtest. Gross-return uplift is conditional on using the quoted sportsbook price and does not model account access, limits, stake rejection or later price movement."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit prospective EPL best-price economics without changing Football 1 probabilities.")
    parser.add_argument("--archive", type=Path, default=Path("prospective/odds_snapshots.jsonl"))
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/price_shopping_audit.json"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = price_shopping_audit(args.archive, args.ledger)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = report["quote_economics"]
    print(
        json.dumps(
            {
                "status": report["status"],
                "event_snapshots": summary["event_snapshots"],
                "outcome_quote_observations": summary["outcome_quote_observations"],
                "price_uplift": summary["price_uplift"],
                "best_price_coverage": summary["best_price_coverage"],
                "locked_snapshot_join": report["locked_snapshot_join"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
