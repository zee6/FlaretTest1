from __future__ import annotations

from football1.model_disagreement import DisagreementRow
from football1.shadow_price_consensus import (
    _group_metrics,
    _market_ranks,
    build_price_consensus_opportunities,
    shadow_price_consensus_from_rows,
)


def _row() -> DisagreementRow:
    market = (0.50, 0.30, 0.20)
    shadows = {
        "elo": (0.55, 0.28, 0.17),
        "bayesian_strength": (0.54, 0.31, 0.15),
        "poisson": (0.52, 0.29, 0.19),
        "dixon_coles": (0.51, 0.32, 0.17),
    }
    return DisagreementRow(
        match_id="m1",
        season_start_year=2025,
        match_date="2025-09-01",
        home_team="Home",
        away_team="Away",
        result="H",
        market_probs=market,
        odds=(1.90, 3.50, 5.00),
        shadow_probs=shadows,
        shadow_mean_probs=(0.53, 0.30, 0.17),
        blended_probs=market,
        market_top="H",
        shadow_consensus_top="H",
        shadow_consensus_count=4,
        market_alignment_count=4,
        probability_dispersion=0.02,
        mean_abs_shadow_market_distance=0.03,
    )


def test_market_ranks_are_deterministic() -> None:
    assert _market_ranks((0.50, 0.30, 0.20)) == [1, 2, 3]


def test_support_count_is_computed_per_outcome() -> None:
    items = build_price_consensus_opportunities([_row()])
    by_outcome = {item.outcome: item for item in items}
    assert by_outcome["H"].support_count == 4
    assert by_outcome["D"].support_count == 2
    assert by_outcome["A"].support_count == 0
    assert by_outcome["H"].market_role == "favorite"
    assert by_outcome["D"].market_role == "non_favorite"


def test_group_metrics_use_bookmaker_roi_and_market_calibration() -> None:
    home = build_price_consensus_opportunities([_row()])[0]
    metrics = _group_metrics([home])
    assert metrics["opportunities"] == 1
    assert metrics["observed_frequency"] == 1.0
    assert metrics["mean_market_probability"] == 0.50
    assert metrics["calibration_gap_observed_minus_market"] == 0.50
    assert metrics["pnl_units"] == 0.90
    assert metrics["roi"] == 0.90


def test_report_keeps_all_support_counts_and_zero_weight_status() -> None:
    report = shadow_price_consensus_from_rows([_row()])
    assert set(report["all_outcomes_by_support_count"].keys()) == {"0", "1", "2", "3", "4"}
    assert report["all_outcomes_by_support_count"]["4"]["opportunities"] == 1
    assert report["all_outcomes_by_support_count"]["0"]["opportunities"] == 1
    assert report["status"] == "historical_retrospective_observer_only_zero_decision_weight"
