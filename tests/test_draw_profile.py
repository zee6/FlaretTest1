from __future__ import annotations

import math

import pytest

from football1.draw_profile import (
    FEATURE_NAMES,
    _binary_metrics,
    _feature_vector,
    _non_loss_probability_audit,
    low_score_draw_mass,
)


def _row() -> dict:
    return {
        "match_id": "m1",
        "season_start_year": 2024,
        "result": "D",
        "probabilities": {
            "market": (0.38, 0.30, 0.32),
            "independent_poisson": (0.36, 0.31, 0.33),
            "dixon_coles": (0.37, 0.32, 0.31),
            "davidson": (0.39, 0.27, 0.34),
            "bivariate_poisson": (0.36, 0.315, 0.325),
            "gamma_frailty": (0.365, 0.31, 0.325),
            "market_plus_fixed_rf_residual": (0.37, 0.315, 0.315),
        },
    }


def test_low_score_draw_mass_is_valid_probability_mass() -> None:
    mass = low_score_draw_mass(1.2, 1.1)
    assert 0.0 < mass < 1.0
    assert mass == pytest.approx(
        sum(
            math.exp(-1.2) * 1.2**g / math.factorial(g)
            * math.exp(-1.1) * 1.1**g / math.factorial(g)
            for g in (0, 1, 2)
        )
    )


def test_feature_vector_contains_elo_balance_and_jury_signals() -> None:
    vector = _feature_vector(
        _row(),
        expected_home_goals=1.25,
        expected_away_goals=1.20,
        elo_diff=-18.0,
    )
    assert len(vector) == len(FEATURE_NAMES)
    values = dict(zip(FEATURE_NAMES, vector))
    assert values["market_draw_probability"] == pytest.approx(0.30)
    assert values["rf_draw_residual_vs_market"] == pytest.approx(0.015)
    assert values["market_home_away_gap"] == pytest.approx(0.06)
    assert values["expected_goal_gap"] == pytest.approx(0.05)
    assert values["absolute_elo_difference"] == pytest.approx(18.0)


def test_binary_metrics_rewards_concentrated_positive_probability() -> None:
    report = _binary_metrics(
        [
            (0.60, True),
            (0.55, True),
            (0.40, False),
            (0.30, False),
            (0.20, False),
        ]
    )
    assert report["base_rate"] == pytest.approx(0.40)
    assert report["auc"] == pytest.approx(1.0)
    assert report["top_20pct"]["observed_rate"] == pytest.approx(1.0)
    assert report["brier"] < 0.20


def test_non_loss_probability_audit_combines_draw_with_each_side() -> None:
    row = _row()
    report = _non_loss_probability_audit([row], [2024])

    assert report["1X"]["retained_rf"]["mean_probability"] == pytest.approx(0.685)
    assert report["X2"]["retained_rf"]["mean_probability"] == pytest.approx(0.63)
    assert report["market_outsider_or_draw"]["market"]["mean_probability"] == pytest.approx(0.62)
