from __future__ import annotations

import pytest

from football1.closing_movement_rf import apply_predicted_movement, _movement_error_summary


def test_apply_predicted_movement_preserves_probability_simplex() -> None:
    opening = (0.50, 0.30, 0.20)
    candidate = apply_predicted_movement(opening, (0.03, -0.01, -0.02))
    assert candidate == pytest.approx((0.53, 0.29, 0.18))
    assert sum(candidate) == pytest.approx(1.0)


def test_apply_predicted_movement_projects_extreme_negative_value() -> None:
    candidate = apply_predicted_movement((0.10, 0.20, 0.70), (-0.50, 0.10, 0.40))
    assert all(value > 0.0 for value in candidate)
    assert sum(candidate) == pytest.approx(1.0)


def test_movement_error_summary_rewards_better_forecast_than_zero_baseline() -> None:
    actual = [(0.03, -0.01, -0.02), (-0.02, 0.01, 0.01)]
    zero = [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)]
    predicted = [(0.025, -0.008, -0.017), (-0.018, 0.009, 0.009)]

    baseline = _movement_error_summary(actual, zero)
    model = _movement_error_summary(actual, predicted)
    assert float(model["mean_abs_error_per_outcome"]) < float(baseline["mean_abs_error_per_outcome"])
    assert float(model["rmse_per_outcome"]) < float(baseline["rmse_per_outcome"])
    assert baseline["direction_evaluated_outcomes"] == 0
    assert baseline["direction_accuracy_nonzero_predictions"] is None
    assert model["direction_evaluated_outcomes"] == 6
    assert model["direction_accuracy_nonzero_predictions"] == pytest.approx(1.0)
