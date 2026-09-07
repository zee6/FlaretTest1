from __future__ import annotations

import math

from football1.draw_jury_audit import _binary_draw_metrics, _score_category


def test_score_category_splits_draw_scorelines() -> None:
    assert _score_category(0, 0) == "0-0"
    assert _score_category(1, 1) == "1-1"
    assert _score_category(2, 2) == "2-2"
    assert _score_category(3, 3) == "other_draw"
    assert _score_category(2, 1) == "non_draw"


def test_draw_metrics_reward_ranking_and_calibration() -> None:
    items = [
        (0.70, True),
        (0.60, True),
        (0.40, False),
        (0.30, False),
        (0.20, False),
        (0.10, False),
    ]
    result = _binary_draw_metrics(items)

    assert result["matches"] == 6
    assert result["draws"] == 2
    assert math.isclose(result["draw_rate"], 1 / 3)
    assert math.isclose(result["draw_auc"], 1.0)
    assert result["draw_brier"] < 0.12
    assert result["top_20pct"]["observed_draw_rate"] == 1.0
    assert result["top_20pct"]["lift_vs_base_rate"] == 3.0


def test_draw_metrics_penalize_reversed_ranking() -> None:
    good = _binary_draw_metrics(
        [(0.7, True), (0.6, True), (0.3, False), (0.2, False)]
    )
    bad = _binary_draw_metrics(
        [(0.2, True), (0.3, True), (0.6, False), (0.7, False)]
    )

    assert good["draw_auc"] == 1.0
    assert bad["draw_auc"] == 0.0
    assert good["draw_brier"] < bad["draw_brier"]
    assert good["draw_log_loss"] < bad["draw_log_loss"]
