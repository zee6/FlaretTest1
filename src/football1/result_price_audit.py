from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from football1.features import FeatureRow, build_feature_rows
from football1.market_baseline import RESULT_INDEX
from football1.offset_slant import _market_probs, fit_offset_slant


OUTCOMES = ("H", "D", "A")
ALPHA = 0.10
MIN_TRAIN_SEASONS = 3


def _quoted_odds(row: FeatureRow) -> tuple[float, float, float]:
    values = (row.b365_home, row.b365_draw, row.b365_away)
    if any(value is None or not math.isfinite(float(value)) or float(value) <= 1.0 for value in values):
        raise ValueError(f"Missing/invalid B365 odds for {row.match_id}")
    return tuple(float(value) for value in values)  # type: ignore[arg-type,return-value]


def _pnl(odds: float, won: bool) -> float:
    return odds - 1.0 if won else -1.0


def _max_drawdown(pnls: list[float]) -> float:
    balance = 0.0
    peak = 0.0
    worst = 0.0
    for pnl in pnls:
        balance += pnl
        peak = max(peak, balance)
        worst = max(worst, peak - balance)
    return worst


def _bet_summary(records: list[dict[str, Any]], *, outcome_key: str, ev_key: str) -> dict[str, Any]:
    if not records:
        return {
            "matches": 0,
            "wins": 0,
            "hit_rate": None,
            "mean_odds": None,
            "mean_model_probability": None,
            "mean_market_probability": None,
            "mean_quoted_break_even_probability": None,
            "mean_model_edge_vs_market": None,
            "mean_market_minus_break_even": None,
            "mean_total_probability_edge_vs_quote": None,
            "mean_raw_model_ev": None,
            "observed_minus_model_probability": None,
            "observed_minus_market_probability": None,
            "pnl_units": 0.0,
            "roi": None,
            "max_drawdown_units": 0.0,
            "by_outcome": {},
            "by_season": {},
        }

    rows: list[dict[str, Any]] = []
    for record in records:
        index = int(record[outcome_key])
        rows.append(
            {
                "outcome": OUTCOMES[index],
                "season": int(record["season_start_year"]),
                "odds": float(record["odds"][index]),
                "model_p": float(record["model_probability"][index]),
                "market_p": float(record["market_probability"][index]),
                "break_even": 1.0 / float(record["odds"][index]),
                "model_edge": float(record["model_probability"][index]) - float(record["market_probability"][index]),
                "quote_edge": float(record["market_probability"][index]) - 1.0 / float(record["odds"][index]),
                "total_edge": float(record["model_probability"][index]) - 1.0 / float(record["odds"][index]),
                "ev": float(record[ev_key]),
                "won": bool(record["result_index"] == index),
            }
        )
    for row in rows:
        row["pnl"] = _pnl(float(row["odds"]), bool(row["won"]))

    n = len(rows)
    wins = sum(bool(row["won"]) for row in rows)
    observed = wins / n
    mean_model = sum(float(row["model_p"]) for row in rows) / n
    mean_market = sum(float(row["market_p"]) for row in rows) / n
    pnl = sum(float(row["pnl"]) for row in rows)

    by_outcome: dict[str, Any] = {}
    for outcome in OUTCOMES:
        subset = [row for row in rows if row["outcome"] == outcome]
        if not subset:
            continue
        sub_pnl = sum(float(row["pnl"]) for row in subset)
        by_outcome[outcome] = {
            "matches": len(subset),
            "wins": sum(bool(row["won"]) for row in subset),
            "hit_rate": sum(bool(row["won"]) for row in subset) / len(subset),
            "mean_odds": sum(float(row["odds"]) for row in subset) / len(subset),
            "mean_model_probability": sum(float(row["model_p"]) for row in subset) / len(subset),
            "mean_market_probability": sum(float(row["market_p"]) for row in subset) / len(subset),
            "mean_model_edge_vs_market": sum(float(row["model_edge"]) for row in subset) / len(subset),
            "mean_raw_model_ev": sum(float(row["ev"]) for row in subset) / len(subset),
            "pnl_units": sub_pnl,
            "roi": sub_pnl / len(subset),
        }

    by_season: dict[str, Any] = {}
    for season in sorted({int(row["season"]) for row in rows}):
        subset = [row for row in rows if int(row["season"]) == season]
        sub_pnl = sum(float(row["pnl"]) for row in subset)
        by_season[str(season)] = {
            "matches": len(subset),
            "wins": sum(bool(row["won"]) for row in subset),
            "hit_rate": sum(bool(row["won"]) for row in subset) / len(subset),
            "mean_raw_model_ev": sum(float(row["ev"]) for row in subset) / len(subset),
            "pnl_units": sub_pnl,
            "roi": sub_pnl / len(subset),
        }

    return {
        "matches": n,
        "wins": wins,
        "hit_rate": observed,
        "mean_odds": sum(float(row["odds"]) for row in rows) / n,
        "mean_model_probability": mean_model,
        "mean_market_probability": mean_market,
        "mean_quoted_break_even_probability": sum(float(row["break_even"]) for row in rows) / n,
        "mean_model_edge_vs_market": sum(float(row["model_edge"]) for row in rows) / n,
        "mean_market_minus_break_even": sum(float(row["quote_edge"]) for row in rows) / n,
        "mean_total_probability_edge_vs_quote": sum(float(row["total_edge"]) for row in rows) / n,
        "mean_raw_model_ev": sum(float(row["ev"]) for row in rows) / n,
        "observed_minus_model_probability": observed - mean_model,
        "observed_minus_market_probability": observed - mean_market,
        "pnl_units": pnl,
        "roi": pnl / n,
        "max_drawdown_units": _max_drawdown([float(row["pnl"]) for row in rows]),
        "by_outcome": by_outcome,
        "by_season": by_season,
    }


def summarize_result_price_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    result_plus_price = [record for record in records if bool(record["result_call_positive_ev"])]
    result_plus_price_and_best = [
        record for record in result_plus_price
        if int(record["result_call_index"]) == int(record["best_ev_index"])
    ]
    alternative_price_interest = [
        record for record in records
        if bool(record["best_ev_positive"])
        and int(record["best_ev_index"]) != int(record["result_call_index"])
    ]
    any_positive_price = [record for record in records if bool(record["best_ev_positive"])]
    no_positive_price = [record for record in records if not bool(record["best_ev_positive"])]

    result_call_accuracy = (
        sum(int(record["result_index"]) == int(record["result_call_index"]) for record in records) / len(records)
        if records
        else None
    )

    return {
        "matches": len(records),
        "result_call_accuracy": result_call_accuracy,
        "classes": {
            "result_plus_price_raw_interest": {
                "definition": "Football 1 H/D/A argmax also has raw model EV > 0 at quoted B365 odds",
                **_bet_summary(result_plus_price, outcome_key="result_call_index", ev_key="result_call_ev"),
            },
            "result_plus_price_and_best_price": {
                "definition": "Result call has raw EV > 0 and is also the highest-EV H/D/A outcome",
                **_bet_summary(result_plus_price_and_best, outcome_key="result_call_index", ev_key="result_call_ev"),
            },
            "alternative_price_raw_interest": {
                "definition": "Highest-EV H/D/A outcome has raw EV > 0 but differs from Football 1 result call",
                **_bet_summary(alternative_price_interest, outcome_key="best_ev_index", ev_key="best_ev"),
            },
            "any_positive_price_raw_interest": {
                "definition": "At least one H/D/A outcome has raw model EV > 0; highest-EV outcome is evaluated",
                **_bet_summary(any_positive_price, outcome_key="best_ev_index", ev_key="best_ev"),
            },
            "no_positive_price": {
                "definition": "No H/D/A outcome has raw model EV > 0 at quoted B365 odds",
                "matches": len(no_positive_price),
            },
        },
    }


def _eligible_rows(db_path: Path) -> list[FeatureRow]:
    return [
        row for row in build_feature_rows(db_path)
        if row.b365_home is not None and row.b365_draw is not None and row.b365_away is not None
    ]


def build_oos_result_price_records(
    db_path: Path,
    *,
    min_train_seasons: int = MIN_TRAIN_SEASONS,
    alpha: float = ALPHA,
) -> tuple[list[dict[str, Any]], list[int]]:
    rows = _eligible_rows(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for result-price audit")

    test_seasons = seasons[min_train_seasons:]
    records: list[dict[str, Any]] = []
    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        earlier = set(seasons[:test_index])
        train = [row for row in rows if row.season_start_year in earlier]
        test = [row for row in rows if row.season_start_year == test_season]
        model = fit_offset_slant(train, alpha=alpha)

        for row in test:
            market = _market_probs(row)
            candidate = model.predict_with_base(row, market)
            odds = _quoted_odds(row)
            evs = tuple(candidate[i] * odds[i] - 1.0 for i in range(3))
            result_call = max(range(3), key=lambda i: candidate[i])
            best_ev = max(range(3), key=lambda i: evs[i])
            records.append(
                {
                    "match_id": row.match_id,
                    "season_start_year": row.season_start_year,
                    "match_date": row.match_date,
                    "result": row.result,
                    "result_index": RESULT_INDEX[row.result],
                    "market_probability": market,
                    "model_probability": candidate,
                    "odds": odds,
                    "ev": evs,
                    "result_call_index": result_call,
                    "result_call": OUTCOMES[result_call],
                    "result_call_ev": evs[result_call],
                    "result_call_positive_ev": evs[result_call] > 0.0,
                    "best_ev_index": best_ev,
                    "best_ev_outcome": OUTCOMES[best_ev],
                    "best_ev": evs[best_ev],
                    "best_ev_positive": evs[best_ev] > 0.0,
                }
            )

    records.sort(key=lambda record: (str(record["match_date"]), str(record["match_id"])))
    return records, test_seasons


def result_price_audit(
    db_path: Path,
    *,
    min_train_seasons: int = MIN_TRAIN_SEASONS,
    alpha: float = ALPHA,
) -> dict[str, Any]:
    records, test_seasons = build_oos_result_price_records(
        db_path,
        min_train_seasons=min_train_seasons,
        alpha=alpha,
    )
    return {
        "experiment": "result_call_plus_price_historical_audit_v1",
        "status": "historical_exploratory_previously_observed_data",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "model": "fixed_market_offset_football_slant_v1",
        "alpha": alpha,
        "market_anchor": "B365 pre-closing de-vigged probabilities; B365 quoted odds for price test",
        "split_policy": "walk-forward by season; each test season fitted only on earlier seasons",
        "test_seasons": test_seasons,
        "raw_interest_definition": (
            "Raw positive EV means model_probability * quoted_decimal_odds - 1 > 0. "
            "Zero is mathematical break-even, not a validated recommendation threshold."
        ),
        "warning": (
            "This audit isolates the product concept 'our favoured result plus a favourable price' on historical OOS predictions. "
            "It does not select a minimum edge or staking rule. The same historical seasons have already been inspected, so results "
            "are diagnostic rather than fresh confirmation. Historical B365 anchoring is not equivalent to the prospective multi-book live anchor."
        ),
        **summarize_result_price_records(records),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the Football 1 result-call-plus-price product class on historical walk-forward predictions."
    )
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/result_price_audit.json"))
    parser.add_argument("--min-train-seasons", type=int, default=MIN_TRAIN_SEASONS)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = result_price_audit(
        args.database,
        min_train_seasons=args.min_train_seasons,
        alpha=args.alpha,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compact = {
        "status": report["status"],
        "decision_weight": report["decision_weight"],
        "matches": report["matches"],
        "result_call_accuracy": report["result_call_accuracy"],
        "classes": {
            name: {
                "matches": block.get("matches"),
                "roi": block.get("roi"),
                "mean_raw_model_ev": block.get("mean_raw_model_ev"),
                "observed_minus_model_probability": block.get("observed_minus_model_probability"),
            }
            for name, block in report["classes"].items()
        },
    }
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
