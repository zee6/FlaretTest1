from __future__ import annotations

import pytest

from football1.market_consensus_baseline_check import mean_movement


def test_mean_movement_is_component_mean_and_zero_sum() -> None:
    result = mean_movement([(0.03, -0.01, -0.02), (-0.01, 0.02, -0.01)])
    assert result == pytest.approx((0.01, 0.005, -0.015))
    assert sum(result) == pytest.approx(0.0)


def test_mean_movement_requires_rows() -> None:
    with pytest.raises(ValueError):
        mean_movement([])
