from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from football1.portfolio_lab import PortfolioConfig, run_strategy_set, simulate_strategy, _flat_stake
from football1.prospective import prediction_content_hash
from football1.settlement import settlement_content_hash


LABELS = ("home", "draw", "away")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _verify_prediction(row: dict[str, Any]) -> None:
    unsigned = dict(row)
    stored = unsigned.pop("content_sha256", None)
    if stored != prediction_content_hash(unsigned):
        raise ValueError(f"Prediction {row.get('record_id')} failed content hash verification")


def _verify_settlement(row: dict[str, Any]) -> None:
    unsigned = dict(row)
    stored = unsigned.pop("content_sha256", None)
    if stored != settlement_content_hash(unsigned):
        raise ValueError(f"Settlement {row.get('settlement_id')} failed content hash verification")


def _outcome_argmax(probability: dict[str, Any]) -> str:
    return max(LABELS, key=lambda label: float(probability[label]))


def _bet(prediction: dict[str, Any], settlement: dict[str, Any], outcome: str, selection_class: str) -> dict[str, Any]:
    if outcome not in LABELS:
        raise ValueError(f"Invalid outcome {outcome}")
    model_probability = float(prediction["model"]["probability"][outcome])
    market_probability = float(prediction["market_anchor"]["probability"][outcome])
    odds = float(prediction["market_anchor"]["best_decimal_odds"][outcome])
    return {
        "match_id": str(prediction["event_id"]),
        "match_date": str(prediction["commence_time_utc"])[:10],
        "season_start_year": int(prediction["features"]["season_start_year"]),
        "outcome": outcome,
        "odds": odds,
        "won": str(settlement["result"]) == outcome,
        "model_probability": model_probability,
        "market_probability": market_probability,
        "raw_model_ev": model_probability * odds - 1.0,
        "selection_class": selection_class,
    }


def build_selection_sets(
    predictions_by_id: dict[str, dict[str, Any]],
    settlements: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    broad: list[dict[str, Any]] = []
    gold: list[dict[str, Any]] = []
    raw_max: list[dict[str, Any]] = []
    favourites: list[dict[str, Any]] = []

    for settlement in settlements:
        prediction_id = str(settlement["prediction_record_id"])
        prediction = predictions_by_id[prediction_id]
        model_probability = prediction["model"]["probability"]
        market_probability = prediction["market_anchor"]["probability"]
        result_call = _outcome_argmax(model_probability)
        market_favourite = _outcome_argmax(market_probability)
        max_ev_outcome = str(prediction["model"]["max_predicted_ev_outcome"])
        if max_ev_outcome not in LABELS:
            raise ValueError(f"Invalid max-EV outcome in {prediction_id}")

        result_call_ev = (
            float(model_probability[result_call])
            * float(prediction["market_anchor"]["best_decimal_odds"][result_call])
            - 1.0
        )
        if result_call_ev > 0.0:
            broad.append(_bet(prediction, settlement, result_call, "result_call_positive_price_interest"))
            if result_call == max_ev_outcome:
                gold.append(_bet(prediction, settlement, result_call, "result_call_and_best_price_interest"))

        raw_max.append(_bet(prediction, settlement, max_ev_outcome, "raw_max_ev_outcome_every_settled_match"))
        favourites.append(_bet(prediction, settlement, market_favourite, "market_favourite_every_settled_match"))

    sort_key = lambda row: (row["match_date"], row["match_id"])
    return {
        "result_call_positive_price_interest": sorted(broad, key=sort_key),
        "result_call_and_best_price_interest": sorted(gold, key=sort_key),
        "raw_max_ev_every_settled_match": sorted(raw_max, key=sort_key),
        "market_favourite_every_settled_match": sorted(favourites, key=sort_key),
    }


def _zero_bet_portfolio(config: PortfolioConfig) -> dict[str, Any]:
    return {
        "strategy": "no_validated_betting_rule",
        "bets_available": 0,
        "bets_placed": 0,
        "wins": 0,
        "hit_rate": None,
        "starting_bankroll": config.starting_bankroll,
        "final_bankroll": config.starting_bankroll,
        "pnl": 0.0,
        "return_on_starting_bankroll": 0.0,
        "total_staked": 0.0,
        "roi_on_turnover": None,
        "mean_stake": None,
        "max_stake": 0.0,
        "max_drawdown_amount": 0.0,
        "max_drawdown_fraction": 0.0,
        "longest_losing_streak": 0,
        "equity_curve": [{"match_date": None, "bankroll": config.starting_bankroll}],
        "journal": [],
    }


def build_report(
    prediction_path: Path,
    settlement_path: Path,
    *,
    config: PortfolioConfig | None = None,
) -> dict[str, Any]:
    cfg = config or PortfolioConfig()
    cfg.validate()
    predictions = _load_jsonl(prediction_path)
    settlements = _load_jsonl(settlement_path)
    for row in predictions:
        _verify_prediction(row)
    for row in settlements:
        _verify_settlement(row)

    predictions_by_id = {str(row["record_id"]): row for row in predictions}
    if len(predictions_by_id) != len(predictions):
        raise ValueError("Duplicate prediction record id")

    for settlement in settlements:
        prediction_id = str(settlement["prediction_record_id"])
        prediction = predictions_by_id.get(prediction_id)
        if prediction is None:
            raise ValueError(f"Settlement references unknown prediction {prediction_id}")
        if str(settlement["prediction_content_sha256"]) != str(prediction["content_sha256"]):
            raise ValueError(f"Settlement prediction hash mismatch {prediction_id}")

    selections = build_selection_sets(predictions_by_id, settlements)
    shadow_portfolios = {
        "result_call_positive_price_interest": run_strategy_set(
            selections["result_call_positive_price_interest"], config=cfg
        ),
        "result_call_and_best_price_interest": run_strategy_set(
            selections["result_call_and_best_price_interest"], config=cfg
        ),
        "raw_max_ev_every_settled_match": run_strategy_set(
            selections["raw_max_ev_every_settled_match"], config=cfg
        ),
    }
    favourite_flat = simulate_strategy(
        selections["market_favourite_every_settled_match"],
        name="market_favourite_every_settled_match_flat_stake",
        config=cfg,
        stake_rule=_flat_stake,
    )

    return {
        "experiment": "prospective_portfolio_observer_v1",
        "status": "prospective_research_zero_decision_weight",
        "settled_records": len(settlements),
        "official_research_portfolio": {
            "policy": "no_validated_betting_rule",
            "reason": (
                "Football 1 currently has no prospectively validated selection threshold. "
                "PASS/no compulsory bet is therefore the only non-hindsight portfolio policy."
            ),
            "portfolio": _zero_bet_portfolio(cfg),
        },
        "shadow_selection_counts": {key: len(value) for key, value in selections.items()},
        "shadow_portfolios": shadow_portfolios,
        "benchmarks": {
            "market_favourite_every_settled_match_flat_stake": favourite_flat,
        },
        "portfolio_config": {
            "starting_bankroll": cfg.starting_bankroll,
            "base_fraction": cfg.base_fraction,
            "flat_stake_amount": cfg.starting_bankroll * cfg.base_fraction,
            "drawdown_scale": cfg.drawdown_scale,
            "drawdown_floor": cfg.drawdown_floor,
            "loss_week_multiplier": cfg.loss_week_multiplier,
            "status": "same_predeclared_illustrative_controls_as_historical_portfolio_lab_v1",
        },
        "selection_definitions": {
            "result_call_positive_price_interest": (
                "Football 1 H/D/A argmax has raw arithmetic EV > 0 at the recorded lock best numeric quote."
            ),
            "result_call_and_best_price_interest": (
                "The Football 1 H/D/A argmax has raw arithmetic EV > 0 and is also the recorded maximum-EV outcome."
            ),
            "raw_max_ev_every_settled_match": (
                "Take the recorded maximum-EV H/D/A outcome on every settled fixture; diagnostic only."
            ),
            "market_favourite_every_settled_match": "Take the de-vigged market H/D/A argmax on every settled fixture.",
        },
        "price_caveat": (
            "The original 4 September lock stored best numeric odds but not bookmaker provenance. "
            "The recorded best may include a raw exchange quote whose commission is unknown. "
            "Shadow P&L is therefore gross research-price P&L, not claimed executable sportsbook performance."
        ),
        "guardrails": [
            "Shadow portfolios are observers, not recommendations.",
            "Raw positive EV is not a validated threshold.",
            "The official research portfolio places no bets until a rule is prospectively validated.",
            "Do not promote a shadow strategy because it wins one matchweek.",
            "Portfolio P&L must never feed back into football probabilities.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report prospective Football 1 portfolio observers.")
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--settlements", type=Path, default=Path("prospective/settlements.jsonl"))
    parser.add_argument("--starting-bankroll", type=float, default=1000.0)
    parser.add_argument("--base-fraction", type=float, default=0.01)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = PortfolioConfig(starting_bankroll=args.starting_bankroll, base_fraction=args.base_fraction)
    report = build_report(args.ledger, args.settlements, config=config)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote prospective portfolio report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
