from __future__ import annotations

import pytest

from football1.minimal_draw_balance_audit import _delta, _fit, _metrics


def test_binary_metrics_are_well_formed() -> None:
    result = _metrics([(0.30, True), (0.20, False), (0.40, True), (0.10, False)])
    assert result["matches"] == 4
    assert result["draws"] == 2
    assert result["draw_rate"] == pytest.approx(0.5)
    assert result["mean_probability"] == pytest.approx(0.25)
    assert 0.0 <= result["brier"] <= 1.0
    assert result["log_loss"] > 0.0
    assert result["auc"] == pytest.approx(1.0)
    assert result["ece"] >= 0.0


def test_delta_uses_candidate_minus_control_direction() -> None:
    candidate = {"brier": 0.17, "log_loss": 0.52, "auc": 0.61, "ece": 0.02}
    control = {"brier": 0.18, "log_loss": 0.54, "auc": 0.59, "ece": 0.01}
    result = _delta(candidate, control)
    assert result["brier"] == pytest.approx(-0.01)
    assert result["log_loss"] == pytest.approx(-0.02)
    assert result["auc"] == pytest.approx(0.02)
    assert result["ece"] == pytest.approx(0.01)


def test_two_feature_logistic_can_learn_balance_direction() -> None:
    # Same market pDraw throughout; draws are deliberately concentrated in
    # smaller H/A gaps so the second feature must carry the distinction.
    features = [
        [0.28, 0.01],
        [0.28, 0.02],
        [0.28, 0.03],
        [0.28, 0.04],
        [0.28, 0.20],
        [0.28, 0.22],
        [0.28, 0.25],
        [0.28, 0.30],
    ]
    targets = [1, 1, 1, 1, 0, 0, 0, 0]
    model = _fit(features, targets)
    coefficient = float(model.named_steps["logistic"].coef_[0][1])
    assert coefficient < 0.0


def test_metrics_handles_empty_input() -> None:
    result = _metrics([])
    assert result["matches"] == 0
    assert result["brier"] is None
    assert result["auc"] is None
