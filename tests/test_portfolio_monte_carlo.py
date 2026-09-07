from __future__ import annotations

import random

import pytest

from football1.portfolio_monte_carlo import (
    benchmark_terminal_value,
    bets_by_source_week,
    build_source_week_universe,
    materialize_sampled_path,
    sample_week_keys,
    summarize_paths,
    week_start,
)


def _record(match_id: str, match_date: str, season: int = 2025) -> dict:
    return {"match_id": match_id, "match_date": match_date, "season_start_year": season}


def _bet(match_id: str, match_date: str) -> dict:
    return {
        "match_id": match_id,
        "match_date": match_date,
        "season_start_year": 2025,
        "outcome_index": 0,
        "outcome": "H",
        "odds": 2.0,
        "won": True,
        "model_probability": 0.55,
        "market_probability": 0.50,
        "raw_model_ev": 0.10,
        "selection_class": "synthetic",
    }


def test_week_start_and_universe_retain_empty_week() -> None:
    records = [
        _record("a", "2025-09-01"),
        _record("b", "2025-09-15"),
    ]
    assert week_start("2025-09-03").isoformat() == "2025-09-01"
    assert build_source_week_universe(records) == [
        "2025-09-01",
        "2025-09-08",
        "2025-09-15",
    ]


def test_materialized_path_preserves_empty_sampled_week_and_weekday() -> None:
    source = bets_by_source_week([_bet("a", "2025-09-03"), _bet("b", "2025-09-16")])
    sampled = ["2025-09-01", "2025-09-08", "2025-09-15"]
    path = materialize_sampled_path(sampled, source, simulation_index=7)

    # 2001-01-01 was Monday. The Wednesday bet stays Wednesday in synthetic week 0.
    assert path[0]["match_date"] == "2001-01-03"
    # The middle source week is empty, so the second bet lands in synthetic week 2.
    assert path[1]["match_date"] == "2001-01-16"
    assert path[0]["match_id"].startswith("mc7-w0-")
    assert path[1]["match_id"].startswith("mc7-w2-")


def test_sample_week_keys_is_seed_deterministic() -> None:
    universe = ["a", "b", "c"]
    first = sample_week_keys(universe, horizon_weeks=8, rng=random.Random(17))
    second = sample_week_keys(universe, horizon_weeks=8, rng=random.Random(17))
    assert first == second
    assert len(first) == 8


def test_benchmark_terminal_value_compounds_fractional_year() -> None:
    value = benchmark_terminal_value(1000.0, 0.04, 26)
    assert value == pytest.approx(1000.0 * (1.04 ** 0.5))


def test_summarize_paths_reports_survival_and_benchmark_frequency() -> None:
    paths = [
        {"final_bankroll": 120.0, "max_drawdown_fraction": 0.10, "bets_placed": 10, "total_staked": 50.0},
        {"final_bankroll": 100.0, "max_drawdown_fraction": 0.30, "bets_placed": 8, "total_staked": 40.0},
        {"final_bankroll": 50.0, "max_drawdown_fraction": 0.60, "bets_placed": 9, "total_staked": 45.0},
        {"final_bankroll": 20.0, "max_drawdown_fraction": 0.80, "bets_placed": 7, "total_staked": 35.0},
    ]
    summary = summarize_paths(paths, starting_bankroll=100.0, benchmark_target=105.0)

    assert summary["probability_finish_above_start"] == pytest.approx(0.25)
    assert summary["probability_finish_above_benchmark"] == pytest.approx(0.25)
    assert summary["probability_terminal_loss_50pct_or_more"] == pytest.approx(0.50)
    assert summary["probability_max_drawdown_at_least_50pct"] == pytest.approx(0.50)
    assert summary["mean_bets_placed"] == pytest.approx(8.5)


def test_invalid_benchmark_and_empty_universe_are_rejected() -> None:
    with pytest.raises(ValueError):
        benchmark_terminal_value(1000.0, -1.0, 40)
    with pytest.raises(ValueError):
        sample_week_keys([], horizon_weeks=40, rng=random.Random(1))
