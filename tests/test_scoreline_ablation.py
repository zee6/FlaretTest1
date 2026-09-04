from __future__ import annotations

import math

import pytest

from football1.features import FEATURE_NAMES, FeatureRow, feature_vector
from football1.scoreline import ScorelineRow
from football1.scoreline_ablation import (
    BASELINE,
    PLUS_SCORELINE,
    SCORELINE_FEATURE_NAMES,
    variant_feature_names,
    variant_vector,
)


def _feature_row() -> FeatureRow:
    return FeatureRow(
        match_id="m1",
        season_start_year=2025,
        match_date="2025-08-10",
        home_team="Alpha",
        away_team="Bravo",
        result="H",
        elo_diff=42.0,
        ppg5_diff=0.1,
        gf5_diff=0.2,
        ga5_diff=-0.1,
        shots5_diff=1.0,
        shots_allowed5_diff=-1.0,
        sot5_diff=0.5,
        sot_allowed5_diff=-0.5,
        ppg10_diff=0.15,
        gf10_diff=0.25,
        ga10_diff=-0.15,
        rest_days_diff=2.0,
        log_prior_games_home=3.0,
        log_prior_games_away=2.5,
        b365_home=2.1,
        b365_draw=3.4,
        b365_away=3.6,
    )


def _scoreline_row() -> ScorelineRow:
    return ScorelineRow(
        match_id="m1",
        season_start_year=2025,
        match_date="2025-08-10",
        home_team="Alpha",
        away_team="Bravo",
        result="H",
        expected_home_goals=1.8,
        expected_away_goals=1.0,
        home_prob=0.55,
        draw_prob=0.25,
        away_prob=0.20,
        top_score_home=1,
        top_score_away=0,
        top_score_prob=0.14,
        market_probs=(0.45, 0.28, 0.27),
    )


def test_baseline_reproduces_original_feature_vector() -> None:
    row = _feature_row()
    assert variant_feature_names(BASELINE) == FEATURE_NAMES
    assert variant_vector(row, BASELINE, {}) == feature_vector(row)


def test_plus_scoreline_appends_only_two_probability_log_ratios() -> None:
    row = _feature_row()
    score = _scoreline_row()
    names = variant_feature_names(PLUS_SCORELINE)
    values = variant_vector(row, PLUS_SCORELINE, {"m1": score})

    assert names[: len(FEATURE_NAMES)] == FEATURE_NAMES
    assert names[len(FEATURE_NAMES) :] == tuple(
        f"scoreline__{name}" for name in SCORELINE_FEATURE_NAMES
    )
    assert values[: len(FEATURE_NAMES)] == feature_vector(row)
    assert values[-2] == pytest.approx(math.log(0.55 / 0.25))
    assert values[-1] == pytest.approx(math.log(0.20 / 0.25))


def test_plus_scoreline_requires_matching_precomputed_row() -> None:
    with pytest.raises(ValueError, match="Missing scoreline row"):
        variant_vector(_feature_row(), PLUS_SCORELINE, {})
