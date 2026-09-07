from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from football1.portfolio_lab import (
    DEFAULT_BASE_FRACTION,
    DEFAULT_DRAWDOWN_FLOOR,
    DEFAULT_DRAWDOWN_SCALE,
    DEFAULT_LOSS_WEEK_MULTIPLIER,
    DEFAULT_STARTING_BANKROLL,
    PortfolioConfig,
    _drawdown_stake,
    _favourite_bets,
    _flat_stake,
    _proportional_stake,
    _selection_bets,
    _weekly_loss_stake,
    simulate_strategy,
)
from football1.result_price_audit import build_oos_result_price_records


DEFAULT_SIMULATIONS = 2000
DEFAULT_HORIZON_WEEKS = 40
DEFAULT_SEED = 17
SYNTHETIC_START_MONDAY = date(2001, 1, 1)


@dataclass(frozen=True)
class MonteCarloConfig:
    simulations: int = DEFAULT_SIMULATIONS
    horizon_weeks: int = DEFAULT_HORIZON_WEEKS
    seed: int = DEFAULT_SEED
    annual_benchmark_rate: float | None = None

    def validate(self) -> None:
        if self.simulations <= 0:
            raise ValueError("simulations must be positive")
        if self.horizon_weeks <= 0:
            raise ValueError("horizon_weeks must be positive")
        if self.annual_benchmark_rate is not None and self.annual_benchmark_rate <= -1.0:
            raise ValueError("annual_benchmark_rate must be greater than -1")


def week_start(value: str) -> date:
    parsed = date.fromisoformat(value[:10])
    return parsed - timedelta(days=parsed.weekday())


def build_source_week_universe(records: list[dict[str, Any]]) -> list[str]:
    """Return every calendar week from first to last OOS match within each season.

    Empty weeks are retained. This matters for the previous-week-loss control and
    prevents a bootstrap from pretending that the last active betting week was
    necessarily the immediately preceding calendar week.
    """
    by_season: dict[int, list[date]] = defaultdict(list)
    for record in records:
        by_season[int(record["season_start_year"])].append(date.fromisoformat(str(record["match_date"])[:10]))

    universe: list[str] = []
    for season in sorted(by_season):
        dates = by_season[season]
        if not dates:
            continue
        cursor = week_start(min(dates).isoformat())
        end = week_start(max(dates).isoformat())
        while cursor <= end:
            universe.append(cursor.isoformat())
            cursor += timedelta(days=7)
    if not universe:
        raise ValueError("No source weeks available")
    return universe


def bets_by_source_week(bets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bet in bets:
        result[week_start(str(bet["match_date"])).isoformat()].append(bet)
    for values in result.values():
        values.sort(key=lambda bet: (str(bet["match_date"]), str(bet["match_id"])))
    return dict(result)


def sample_week_keys(universe: list[str], *, horizon_weeks: int, rng: random.Random) -> list[str]:
    if not universe:
        raise ValueError("universe must not be empty")
    if horizon_weeks <= 0:
        raise ValueError("horizon_weeks must be positive")
    return [universe[rng.randrange(len(universe))] for _ in range(horizon_weeks)]


def materialize_sampled_path(
    sampled_week_keys: list[str],
    source: dict[str, list[dict[str, Any]]],
    *,
    simulation_index: int,
) -> list[dict[str, Any]]:
    """Map sampled source weeks onto a synthetic chronological calendar.

    Week positions advance even when a sampled source week has no qualifying
    bets. Within-week weekday offsets are preserved.
    """
    path: list[dict[str, Any]] = []
    for week_index, source_key in enumerate(sampled_week_keys):
        source_monday = date.fromisoformat(source_key)
        target_monday = SYNTHETIC_START_MONDAY + timedelta(days=7 * week_index)
        for bet_index, bet in enumerate(source.get(source_key, [])):
            original = date.fromisoformat(str(bet["match_date"])[:10])
            weekday_offset = (original - source_monday).days
            copied = dict(bet)
            copied["match_date"] = (target_monday + timedelta(days=weekday_offset)).isoformat()
            copied["match_id"] = f"mc{simulation_index}-w{week_index}-b{bet_index}-{bet['match_id']}"
            path.append(copied)
    return path


def benchmark_terminal_value(starting_bankroll: float, annual_rate: float, horizon_weeks: int) -> float:
    if starting_bankroll <= 0:
        raise ValueError("starting_bankroll must be positive")
    if annual_rate <= -1.0:
        raise ValueError("annual_rate must be greater than -1")
    if horizon_weeks <= 0:
        raise ValueError("horizon_weeks must be positive")
    return starting_bankroll * (1.0 + annual_rate) ** (horizon_weeks / 52.0)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    fraction = position - lo
    return ordered[lo] * (1.0 - fraction) + ordered[hi] * fraction


def summarize_paths(
    paths: list[dict[str, Any]],
    *,
    starting_bankroll: float,
    benchmark_target: float | None,
) -> dict[str, Any]:
    if not paths:
        raise ValueError("paths must not be empty")
    terminal = [float(path["final_bankroll"]) for path in paths]
    max_dd = [float(path["max_drawdown_fraction"]) for path in paths]
    placed = [float(path["bets_placed"]) for path in paths]
    total_staked = [float(path["total_staked"]) for path in paths]
    worst_count = max(1, int(len(terminal) * 0.05))
    worst_terminals = sorted(terminal)[:worst_count]

    result: dict[str, Any] = {
        "paths": len(paths),
        "terminal_bankroll": {
            "mean": sum(terminal) / len(terminal),
            "p05": _quantile(terminal, 0.05),
            "p25": _quantile(terminal, 0.25),
            "median": _quantile(terminal, 0.50),
            "p75": _quantile(terminal, 0.75),
            "p95": _quantile(terminal, 0.95),
            "worst_5pct_mean": sum(worst_terminals) / len(worst_terminals),
        },
        "max_drawdown_fraction": {
            "median": _quantile(max_dd, 0.50),
            "p75": _quantile(max_dd, 0.75),
            "p90": _quantile(max_dd, 0.90),
            "p95": _quantile(max_dd, 0.95),
        },
        "probability_finish_above_start": sum(value > starting_bankroll for value in terminal) / len(terminal),
        "probability_terminal_loss_25pct_or_more": sum(value <= 0.75 * starting_bankroll for value in terminal) / len(terminal),
        "probability_terminal_loss_50pct_or_more": sum(value <= 0.50 * starting_bankroll for value in terminal) / len(terminal),
        "probability_max_drawdown_at_least_25pct": sum(value >= 0.25 for value in max_dd) / len(max_dd),
        "probability_max_drawdown_at_least_50pct": sum(value >= 0.50 for value in max_dd) / len(max_dd),
        "probability_max_drawdown_at_least_75pct": sum(value >= 0.75 for value in max_dd) / len(max_dd),
        "mean_bets_placed": sum(placed) / len(placed),
        "mean_total_staked": sum(total_staked) / len(total_staked),
    }
    if benchmark_target is not None:
        result["benchmark_target"] = benchmark_target
        result["probability_finish_above_benchmark"] = sum(value > benchmark_target for value in terminal) / len(terminal)
    else:
        result["benchmark_target"] = None
        result["probability_finish_above_benchmark"] = None
    return result


def portfolio_monte_carlo(
    db_path: Path,
    *,
    simulations: int = DEFAULT_SIMULATIONS,
    horizon_weeks: int = DEFAULT_HORIZON_WEEKS,
    seed: int = DEFAULT_SEED,
    annual_benchmark_rate: float | None = None,
    starting_bankroll: float = DEFAULT_STARTING_BANKROLL,
    base_fraction: float = DEFAULT_BASE_FRACTION,
    drawdown_scale: float = DEFAULT_DRAWDOWN_SCALE,
    drawdown_floor: float = DEFAULT_DRAWDOWN_FLOOR,
    loss_week_multiplier: float = DEFAULT_LOSS_WEEK_MULTIPLIER,
) -> dict[str, Any]:
    mc = MonteCarloConfig(
        simulations=simulations,
        horizon_weeks=horizon_weeks,
        seed=seed,
        annual_benchmark_rate=annual_benchmark_rate,
    )
    mc.validate()
    portfolio = PortfolioConfig(
        starting_bankroll=starting_bankroll,
        base_fraction=base_fraction,
        drawdown_scale=drawdown_scale,
        drawdown_floor=drawdown_floor,
        loss_week_multiplier=loss_week_multiplier,
    )
    portfolio.validate()

    records, test_seasons = build_oos_result_price_records(db_path)
    universe = build_source_week_universe(records)
    gold_source = bets_by_source_week(_selection_bets(records, best_only=True))
    favourite_source = bets_by_source_week(_favourite_bets(records))

    benchmark_target = None
    if annual_benchmark_rate is not None:
        benchmark_target = benchmark_terminal_value(starting_bankroll, annual_benchmark_rate, horizon_weeks)

    strategy_rules = {
        "flat_stake": _flat_stake,
        "bankroll_proportional": _proportional_stake,
        "drawdown_throttle": _drawdown_stake,
        "previous_week_loss_throttle": _weekly_loss_stake,
    }
    path_reports: dict[str, list[dict[str, Any]]] = {name: [] for name in strategy_rules}
    favourite_paths: list[dict[str, Any]] = []

    rng = random.Random(seed)
    for simulation_index in range(simulations):
        sampled = sample_week_keys(universe, horizon_weeks=horizon_weeks, rng=rng)
        gold_path = materialize_sampled_path(sampled, gold_source, simulation_index=simulation_index)
        favourite_path = materialize_sampled_path(sampled, favourite_source, simulation_index=simulation_index)

        for name, rule in strategy_rules.items():
            path_reports[name].append(
                simulate_strategy(gold_path, name=name, config=portfolio, stake_rule=rule)
            )
        favourite_paths.append(
            simulate_strategy(
                favourite_path,
                name="market_favourite_every_match_flat_stake",
                config=portfolio,
                stake_rule=_flat_stake,
            )
        )

    summaries = {
        name: summarize_paths(paths, starting_bankroll=starting_bankroll, benchmark_target=benchmark_target)
        for name, paths in path_reports.items()
    }
    favourite_summary = summarize_paths(
        favourite_paths,
        starting_bankroll=starting_bankroll,
        benchmark_target=benchmark_target,
    )

    return {
        "experiment": "portfolio_week_block_monte_carlo_v1",
        "status": "historical_exploratory_previously_observed_data",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "source_model": "fixed_market_offset_football_slant_v1",
        "selection_class": "result_plus_price_and_best_price",
        "test_seasons": test_seasons,
        "bootstrap": {
            "method": "calendar-week block bootstrap with replacement",
            "source_weeks": len(universe),
            "empty_source_weeks_retained": True,
            "simulations": simulations,
            "horizon_weeks": horizon_weeks,
            "seed": seed,
            "same_sampled_weeks_across_strategies": True,
            "reason": (
                "Weekly blocks preserve within-week clustering better than independently shuffling bets. "
                "This is a distribution stress test, not a proof that future weeks are iid."
            ),
        },
        "portfolio_config": {
            "starting_bankroll": starting_bankroll,
            "base_fraction": base_fraction,
            "drawdown_scale": drawdown_scale,
            "drawdown_floor": drawdown_floor,
            "loss_week_multiplier": loss_week_multiplier,
        },
        "benchmark": {
            "annual_rate": annual_benchmark_rate,
            "terminal_target": benchmark_target,
            "policy": (
                "Optional generic annual hurdle only. A Treasury comparison must use a contemporaneous, currency-consistent benchmark "
                "and must not label an illustrative rate as an observed Treasury return."
            ),
        },
        "gold_standard": summaries,
        "market_favourite_benchmark": favourite_summary,
        "governance": {
            "staking_system_creates_edge": False,
            "purpose": "estimate path risk, capital survival and benchmark-beating frequency under historically observed week blocks",
            "martingale_or_loss_chasing_enabled": False,
            "kelly_enabled": False,
            "conviction_upside_sizing_enabled": False,
        },
        "warning": (
            "Monte Carlo resampling cannot convert a historically negative selection edge into a positive one. It estimates the range of "
            "possible bankroll paths under the observed historical distribution. Results remain exploratory because the source seasons have "
            "already been inspected and future football/odds regimes may differ."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the zero-weight Football 1 portfolio Monte Carlo survival laboratory.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/portfolio_monte_carlo.json"))
    parser.add_argument("--simulations", type=int, default=DEFAULT_SIMULATIONS)
    parser.add_argument("--horizon-weeks", type=int, default=DEFAULT_HORIZON_WEEKS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--annual-benchmark-rate", type=float)
    parser.add_argument("--starting-bankroll", type=float, default=DEFAULT_STARTING_BANKROLL)
    parser.add_argument("--base-fraction", type=float, default=DEFAULT_BASE_FRACTION)
    parser.add_argument("--drawdown-scale", type=float, default=DEFAULT_DRAWDOWN_SCALE)
    parser.add_argument("--drawdown-floor", type=float, default=DEFAULT_DRAWDOWN_FLOOR)
    parser.add_argument("--loss-week-multiplier", type=float, default=DEFAULT_LOSS_WEEK_MULTIPLIER)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = portfolio_monte_carlo(
        args.database,
        simulations=args.simulations,
        horizon_weeks=args.horizon_weeks,
        seed=args.seed,
        annual_benchmark_rate=args.annual_benchmark_rate,
        starting_bankroll=args.starting_bankroll,
        base_fraction=args.base_fraction,
        drawdown_scale=args.drawdown_scale,
        drawdown_floor=args.drawdown_floor,
        loss_week_multiplier=args.loss_week_multiplier,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "bootstrap": report["bootstrap"],
                "benchmark": report["benchmark"],
                "gold_standard": report["gold_standard"],
                "market_favourite_benchmark": report["market_favourite_benchmark"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
