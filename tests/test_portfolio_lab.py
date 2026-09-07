from __future__ import annotations

import pytest

from football1.portfolio_lab import (
    PortfolioConfig,
    _drawdown_stake,
    _flat_stake,
    _proportional_stake,
    _weekly_loss_stake,
    simulate_strategy,
)


def _bet(match_id: str, match_date: str, *, odds: float = 2.0, won: bool = False) -> dict:
    return {
        "match_id": match_id,
        "match_date": match_date,
        "season_start_year": 2025,
        "outcome_index": 0,
        "outcome": "H",
        "odds": odds,
        "won": won,
        "model_probability": 0.55,
        "market_probability": 0.50,
        "raw_model_ev": 0.10,
        "selection_class": "synthetic",
    }


def test_flat_stake_is_unchanged_after_loss() -> None:
    config = PortfolioConfig(starting_bankroll=1000.0, base_fraction=0.01)
    report = simulate_strategy(
        [_bet("a", "2025-09-01", won=False), _bet("b", "2025-09-02", won=True)],
        name="flat",
        config=config,
        stake_rule=_flat_stake,
    )

    assert [entry["stake"] for entry in report["journal"]] == pytest.approx([10.0, 10.0])
    assert report["final_bankroll"] == pytest.approx(1000.0)
    assert report["total_staked"] == pytest.approx(20.0)


def test_bankroll_proportional_stake_contracts_after_loss() -> None:
    config = PortfolioConfig(starting_bankroll=1000.0, base_fraction=0.01)
    report = simulate_strategy(
        [_bet("a", "2025-09-01", won=False), _bet("b", "2025-09-02", won=True)],
        name="proportional",
        config=config,
        stake_rule=_proportional_stake,
    )

    assert report["journal"][0]["stake"] == pytest.approx(10.0)
    assert report["journal"][1]["stake"] == pytest.approx(9.9)
    assert report["final_bankroll"] == pytest.approx(999.9)


def test_drawdown_throttle_reduces_risk_without_changing_probability() -> None:
    config = PortfolioConfig(
        starting_bankroll=1000.0,
        base_fraction=0.10,
        drawdown_scale=0.20,
        drawdown_floor=0.25,
    )
    report = simulate_strategy(
        [_bet("a", "2025-09-01", won=False), _bet("b", "2025-09-02", won=True)],
        name="drawdown",
        config=config,
        stake_rule=_drawdown_stake,
    )

    first, second = report["journal"]
    assert first["stake"] == pytest.approx(100.0)
    # After a 10% drawdown with a 20% scale, the multiplier is 0.5.
    assert second["stake_multiplier"] == pytest.approx(0.5)
    assert second["stake"] == pytest.approx(45.0)
    assert second["model_probability"] == pytest.approx(first["model_probability"])


def test_previous_week_loss_throttle_only_uses_completed_prior_week() -> None:
    config = PortfolioConfig(starting_bankroll=1000.0, base_fraction=0.01, loss_week_multiplier=0.5)
    report = simulate_strategy(
        [
            _bet("a", "2025-09-01", won=False),  # ISO week 36
            _bet("b", "2025-09-02", won=False),  # same week: no throttle yet
            _bet("c", "2025-09-08", won=True),   # week 37: week 36 was negative
            _bet("d", "2025-09-09", won=True),   # same week: still uses week 36 state
            _bet("e", "2025-09-15", won=True),   # week 38: week 37 was positive
        ],
        name="weekly",
        config=config,
        stake_rule=_weekly_loss_stake,
    )

    multipliers = [entry["stake_multiplier"] for entry in report["journal"]]
    assert multipliers == pytest.approx([1.0, 1.0, 0.5, 0.5, 1.0])
    assert report["journal"][2]["previous_week_pnl_for_sizing"] < 0.0
    assert report["journal"][4]["previous_week_pnl_for_sizing"] > 0.0


def test_previous_week_loss_throttle_resets_after_empty_week() -> None:
    config = PortfolioConfig(starting_bankroll=1000.0, base_fraction=0.01, loss_week_multiplier=0.5)
    report = simulate_strategy(
        [
            _bet("a", "2025-09-01", won=False),  # week 36 loses
            # week 37 has no bets
            _bet("b", "2025-09-15", won=True),   # week 38 must not inherit week 36 loss
        ],
        name="weekly-gap",
        config=config,
        stake_rule=_weekly_loss_stake,
    )

    assert [entry["stake_multiplier"] for entry in report["journal"]] == pytest.approx([1.0, 1.0])
    assert report["journal"][1]["previous_week_pnl_for_sizing"] == pytest.approx(0.0)


def test_drawdown_metrics_and_journal_are_deterministic() -> None:
    config = PortfolioConfig(starting_bankroll=100.0, base_fraction=0.10)
    report = simulate_strategy(
        [
            _bet("a", "2025-09-01", odds=2.0, won=True),
            _bet("b", "2025-09-02", odds=2.0, won=False),
            _bet("c", "2025-09-03", odds=2.0, won=False),
        ],
        name="flat",
        config=config,
        stake_rule=_flat_stake,
    )

    assert report["final_bankroll"] == pytest.approx(90.0)
    assert report["max_drawdown_amount"] == pytest.approx(20.0)
    assert report["max_drawdown_fraction"] == pytest.approx(20.0 / 110.0)
    assert report["longest_losing_streak"] == 2
    assert len(report["equity_curve"]) == 4
    assert report["journal"][-1]["post_bankroll"] == pytest.approx(90.0)


def test_invalid_portfolio_parameters_are_rejected() -> None:
    with pytest.raises(ValueError):
        PortfolioConfig(starting_bankroll=0.0).validate()
    with pytest.raises(ValueError):
        PortfolioConfig(base_fraction=0.0).validate()
    with pytest.raises(ValueError):
        PortfolioConfig(drawdown_scale=0.0).validate()
    with pytest.raises(ValueError):
        PortfolioConfig(loss_week_multiplier=1.1).validate()
