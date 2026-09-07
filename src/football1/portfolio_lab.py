from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from football1.result_price_audit import OUTCOMES, build_oos_result_price_records


DEFAULT_STARTING_BANKROLL = 1000.0
DEFAULT_BASE_FRACTION = 0.01
DEFAULT_DRAWDOWN_SCALE = 0.20
DEFAULT_DRAWDOWN_FLOOR = 0.25
DEFAULT_LOSS_WEEK_MULTIPLIER = 0.50


@dataclass(frozen=True)
class PortfolioConfig:
    starting_bankroll: float = DEFAULT_STARTING_BANKROLL
    base_fraction: float = DEFAULT_BASE_FRACTION
    drawdown_scale: float = DEFAULT_DRAWDOWN_SCALE
    drawdown_floor: float = DEFAULT_DRAWDOWN_FLOOR
    loss_week_multiplier: float = DEFAULT_LOSS_WEEK_MULTIPLIER

    def validate(self) -> None:
        if self.starting_bankroll <= 0:
            raise ValueError("starting_bankroll must be positive")
        if not 0 < self.base_fraction <= 1:
            raise ValueError("base_fraction must be in (0, 1]")
        if self.drawdown_scale <= 0:
            raise ValueError("drawdown_scale must be positive")
        if not 0 <= self.drawdown_floor <= 1:
            raise ValueError("drawdown_floor must be in [0, 1]")
        if not 0 <= self.loss_week_multiplier <= 1:
            raise ValueError("loss_week_multiplier must be in [0, 1]")


def _result_plus_price_and_best(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if bool(record["result_call_positive_ev"])
        and int(record["result_call_index"]) == int(record["best_ev_index"])
    ]


def _result_plus_price(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if bool(record["result_call_positive_ev"])]


def _selection_bets(records: list[dict[str, Any]], *, best_only: bool) -> list[dict[str, Any]]:
    selected = _result_plus_price_and_best(records) if best_only else _result_plus_price(records)
    bets: list[dict[str, Any]] = []
    for record in selected:
        index = int(record["result_call_index"])
        bets.append(
            {
                "match_id": record["match_id"],
                "match_date": str(record["match_date"]),
                "season_start_year": int(record["season_start_year"]),
                "outcome_index": index,
                "outcome": OUTCOMES[index],
                "odds": float(record["odds"][index]),
                "won": int(record["result_index"]) == index,
                "model_probability": float(record["model_probability"][index]),
                "market_probability": float(record["market_probability"][index]),
                "raw_model_ev": float(record["ev"][index]),
                "selection_class": "result_plus_price_and_best_price" if best_only else "result_plus_price_raw_interest",
            }
        )
    return sorted(bets, key=lambda bet: (bet["match_date"], bet["match_id"]))


def _favourite_bets(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    for record in records:
        index = max(range(3), key=lambda i: float(record["market_probability"][i]))
        bets.append(
            {
                "match_id": record["match_id"],
                "match_date": str(record["match_date"]),
                "season_start_year": int(record["season_start_year"]),
                "outcome_index": index,
                "outcome": OUTCOMES[index],
                "odds": float(record["odds"][index]),
                "won": int(record["result_index"]) == index,
                "model_probability": float(record["model_probability"][index]),
                "market_probability": float(record["market_probability"][index]),
                "raw_model_ev": float(record["model_probability"][index]) * float(record["odds"][index]) - 1.0,
                "selection_class": "market_favourite_every_match",
            }
        )
    return sorted(bets, key=lambda bet: (bet["match_date"], bet["match_id"]))


def _iso_week(value: str) -> tuple[int, int]:
    parsed = date.fromisoformat(value[:10])
    iso = parsed.isocalendar()
    return int(iso.year), int(iso.week)


def _flat_stake(config: PortfolioConfig, state: dict[str, float], context: dict[str, Any]) -> tuple[float, float]:
    del state, context
    return config.starting_bankroll * config.base_fraction, 1.0


def _proportional_stake(config: PortfolioConfig, state: dict[str, float], context: dict[str, Any]) -> tuple[float, float]:
    del context
    return state["bankroll"] * config.base_fraction, 1.0


def _drawdown_stake(config: PortfolioConfig, state: dict[str, float], context: dict[str, Any]) -> tuple[float, float]:
    del context
    peak = max(state["peak"], config.starting_bankroll)
    drawdown_fraction = (peak - state["bankroll"]) / peak if peak > 0 else 0.0
    multiplier = max(config.drawdown_floor, 1.0 - drawdown_fraction / config.drawdown_scale)
    return state["bankroll"] * config.base_fraction * multiplier, multiplier


def _weekly_loss_stake(config: PortfolioConfig, state: dict[str, float], context: dict[str, Any]) -> tuple[float, float]:
    del state
    multiplier = config.loss_week_multiplier if context.get("previous_week_pnl", 0.0) < 0.0 else 1.0
    return context["bankroll"] * config.base_fraction * multiplier, multiplier


StakeRule = Callable[[PortfolioConfig, dict[str, float], dict[str, Any]], tuple[float, float]]


def simulate_strategy(
    bets: list[dict[str, Any]],
    *,
    name: str,
    config: PortfolioConfig,
    stake_rule: StakeRule,
) -> dict[str, Any]:
    config.validate()
    bankroll = float(config.starting_bankroll)
    peak = bankroll
    total_staked = 0.0
    wins = 0
    losing_streak = 0
    longest_losing_streak = 0
    max_drawdown_amount = 0.0
    max_drawdown_fraction = 0.0
    journal: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = [{"match_date": None, "bankroll": bankroll}]

    current_week: tuple[int, int] | None = None
    current_week_pnl = 0.0
    previous_week_pnl = 0.0

    for bet_number, bet in enumerate(bets, start=1):
        week = _iso_week(str(bet["match_date"]))
        if current_week is None:
            current_week = week
        elif week != current_week:
            previous_week_pnl = current_week_pnl
            current_week_pnl = 0.0
            current_week = week

        if bankroll <= 0.0:
            break

        state = {"bankroll": bankroll, "peak": peak}
        context = {
            "bankroll": bankroll,
            "previous_week_pnl": previous_week_pnl,
            "week": week,
        }
        proposed_stake, multiplier = stake_rule(config, state, context)
        stake = max(0.0, min(float(proposed_stake), bankroll))
        if stake <= 0.0:
            continue

        pre_bankroll = bankroll
        won = bool(bet["won"])
        pnl = stake * (float(bet["odds"]) - 1.0) if won else -stake
        bankroll += pnl
        current_week_pnl += pnl
        total_staked += stake
        wins += int(won)

        if won:
            losing_streak = 0
        else:
            losing_streak += 1
            longest_losing_streak = max(longest_losing_streak, losing_streak)

        peak = max(peak, bankroll)
        drawdown_amount = peak - bankroll
        drawdown_fraction = drawdown_amount / peak if peak > 0 else 0.0
        max_drawdown_amount = max(max_drawdown_amount, drawdown_amount)
        max_drawdown_fraction = max(max_drawdown_fraction, drawdown_fraction)

        journal.append(
            {
                "bet_number": bet_number,
                "match_id": bet["match_id"],
                "match_date": bet["match_date"],
                "week": [week[0], week[1]],
                "selection_class": bet["selection_class"],
                "outcome": bet["outcome"],
                "odds": float(bet["odds"]),
                "won": won,
                "model_probability": float(bet["model_probability"]),
                "market_probability": float(bet["market_probability"]),
                "raw_model_ev": float(bet["raw_model_ev"]),
                "pre_bankroll": pre_bankroll,
                "stake": stake,
                "stake_multiplier": float(multiplier),
                "pnl": pnl,
                "post_bankroll": bankroll,
                "peak_bankroll": peak,
                "drawdown_amount": drawdown_amount,
                "drawdown_fraction": drawdown_fraction,
                "previous_week_pnl_for_sizing": previous_week_pnl,
            }
        )
        equity_curve.append({"match_date": bet["match_date"], "bankroll": bankroll})

    pnl_total = bankroll - config.starting_bankroll
    return {
        "strategy": name,
        "bets_available": len(bets),
        "bets_placed": len(journal),
        "wins": wins,
        "hit_rate": wins / len(journal) if journal else None,
        "starting_bankroll": config.starting_bankroll,
        "final_bankroll": bankroll,
        "pnl": pnl_total,
        "return_on_starting_bankroll": pnl_total / config.starting_bankroll,
        "total_staked": total_staked,
        "roi_on_turnover": pnl_total / total_staked if total_staked else None,
        "mean_stake": total_staked / len(journal) if journal else None,
        "max_stake": max((float(entry["stake"]) for entry in journal), default=0.0),
        "max_drawdown_amount": max_drawdown_amount,
        "max_drawdown_fraction": max_drawdown_fraction,
        "longest_losing_streak": longest_losing_streak,
        "equity_curve": equity_curve,
        "journal": journal,
    }


def run_strategy_set(bets: list[dict[str, Any]], *, config: PortfolioConfig) -> dict[str, Any]:
    return {
        "flat_stake": simulate_strategy(bets, name="flat_stake", config=config, stake_rule=_flat_stake),
        "bankroll_proportional": simulate_strategy(
            bets, name="bankroll_proportional", config=config, stake_rule=_proportional_stake
        ),
        "drawdown_throttle": simulate_strategy(
            bets, name="drawdown_throttle", config=config, stake_rule=_drawdown_stake
        ),
        "previous_week_loss_throttle": simulate_strategy(
            bets, name="previous_week_loss_throttle", config=config, stake_rule=_weekly_loss_stake
        ),
    }


def portfolio_lab(
    db_path: Path,
    *,
    starting_bankroll: float = DEFAULT_STARTING_BANKROLL,
    base_fraction: float = DEFAULT_BASE_FRACTION,
    drawdown_scale: float = DEFAULT_DRAWDOWN_SCALE,
    drawdown_floor: float = DEFAULT_DRAWDOWN_FLOOR,
    loss_week_multiplier: float = DEFAULT_LOSS_WEEK_MULTIPLIER,
) -> dict[str, Any]:
    records, test_seasons = build_oos_result_price_records(db_path)
    config = PortfolioConfig(
        starting_bankroll=starting_bankroll,
        base_fraction=base_fraction,
        drawdown_scale=drawdown_scale,
        drawdown_floor=drawdown_floor,
        loss_week_multiplier=loss_week_multiplier,
    )
    config.validate()

    gold_bets = _selection_bets(records, best_only=True)
    broad_bets = _selection_bets(records, best_only=False)
    favourite_bets = _favourite_bets(records)

    return {
        "experiment": "portfolio_laboratory_historical_v1",
        "status": "historical_exploratory_previously_observed_data",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "test_seasons": test_seasons,
        "source_model": "fixed_market_offset_football_slant_v1",
        "selection_policy": {
            "gold_standard": (
                "Football 1 result-call H/D/A argmax has raw model EV > 0 at quoted B365 odds and is also the highest-EV outcome."
            ),
            "broad_result_plus_price": "Football 1 result-call H/D/A argmax has raw model EV > 0 at quoted B365 odds.",
            "favourite_benchmark": "Bet the de-vigged B365 market favourite in every eligible OOS match.",
            "warning": "Raw EV > 0 is mathematical break-even only; it is not a validated recommendation threshold.",
        },
        "portfolio_config": {
            "starting_bankroll": config.starting_bankroll,
            "base_fraction": config.base_fraction,
            "flat_stake_amount": config.starting_bankroll * config.base_fraction,
            "drawdown_scale": config.drawdown_scale,
            "drawdown_floor": config.drawdown_floor,
            "loss_week_multiplier": config.loss_week_multiplier,
            "parameter_status": "predeclared illustrative risk controls; not historically optimized",
        },
        "strategy_definitions": {
            "flat_stake": "Constant base_fraction of starting bankroll on every selected bet.",
            "bankroll_proportional": "Constant base_fraction of current bankroll on every selected bet.",
            "drawdown_throttle": (
                "Current-bankroll proportional stake multiplied by max(drawdown_floor, 1 - current_drawdown_fraction/drawdown_scale)."
            ),
            "previous_week_loss_throttle": (
                "Current-bankroll proportional stake; if the immediately preceding ISO week's portfolio P&L was negative, multiply stake by loss_week_multiplier."
            ),
        },
        "governance": {
            "previous_losses_change_probability": False,
            "previous_losses_may_change_risk_budget": True,
            "rank_weighted_staking_enabled": False,
            "rank_weighted_reason": (
                "Residual-magnitude audit found larger Football 1 deviations were not more reliable; no evidence-based sizing rank exists yet."
            ),
            "kelly_enabled": False,
            "kelly_reason": "Football 1 fair probabilities remain insufficiently calibrated for Kelly-style sizing.",
        },
        "selection_sets": {
            "gold_standard": {
                "bets": len(gold_bets),
                "strategies": run_strategy_set(gold_bets, config=config),
            },
            "broad_result_plus_price": {
                "bets": len(broad_bets),
                "strategies": run_strategy_set(broad_bets, config=config),
            },
        },
        "benchmarks": {
            "market_favourite_every_match_flat_stake": simulate_strategy(
                favourite_bets,
                name="market_favourite_every_match_flat_stake",
                config=config,
                stake_rule=_flat_stake,
            )
        },
        "ui_contract_future": {
            "portfolio_page_deferred": True,
            "chart_series_available": [
                "gold_standard.flat_stake",
                "gold_standard.bankroll_proportional",
                "gold_standard.drawdown_throttle",
                "gold_standard.previous_week_loss_throttle",
                "market_favourite_every_match_flat_stake",
            ],
            "journal_fields": [
                "match_date",
                "outcome",
                "odds",
                "stake",
                "pnl",
                "post_bankroll",
                "drawdown_fraction",
            ],
        },
        "warning": (
            "This is a capital-management laboratory on historical seasons that have already been inspected. It does not validate the selection policy, "
            "stake fractions, drawdown response, or previous-week-loss response. Strategy comparisons must be interpreted as risk-control diagnostics, "
            "not as evidence of a profitable betting system."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the zero-weight Football 1 historical portfolio laboratory.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/portfolio_lab.json"))
    parser.add_argument("--starting-bankroll", type=float, default=DEFAULT_STARTING_BANKROLL)
    parser.add_argument("--base-fraction", type=float, default=DEFAULT_BASE_FRACTION)
    parser.add_argument("--drawdown-scale", type=float, default=DEFAULT_DRAWDOWN_SCALE)
    parser.add_argument("--drawdown-floor", type=float, default=DEFAULT_DRAWDOWN_FLOOR)
    parser.add_argument("--loss-week-multiplier", type=float, default=DEFAULT_LOSS_WEEK_MULTIPLIER)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = portfolio_lab(
        args.database,
        starting_bankroll=args.starting_bankroll,
        base_fraction=args.base_fraction,
        drawdown_scale=args.drawdown_scale,
        drawdown_floor=args.drawdown_floor,
        loss_week_multiplier=args.loss_week_multiplier,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def compact(strategy: dict[str, Any]) -> dict[str, Any]:
        return {
            "bets": strategy["bets_placed"],
            "final_bankroll": strategy["final_bankroll"],
            "roi_on_turnover": strategy["roi_on_turnover"],
            "max_drawdown_fraction": strategy["max_drawdown_fraction"],
            "longest_losing_streak": strategy["longest_losing_streak"],
        }

    print(
        json.dumps(
            {
                "status": report["status"],
                "decision_weight": report["decision_weight"],
                "gold_standard": {
                    name: compact(value)
                    for name, value in report["selection_sets"]["gold_standard"]["strategies"].items()
                },
                "favourite_benchmark": compact(report["benchmarks"]["market_favourite_every_match_flat_stake"]),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
