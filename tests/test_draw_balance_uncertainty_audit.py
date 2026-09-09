from __future__ import annotations

import pytest

from football1.draw_balance_uncertainty_audit import (
    binomial_upper_tail,
    holm_adjust,
    poisson_binomial_upper_tail,
)


def test_poisson_binomial_matches_simple_two_coin_case() -> None:
    # P(X >= 1) for p=.2 and p=.3 = 1 - .8*.7 = .44
    assert poisson_binomial_upper_tail([0.2, 0.3], 1) == pytest.approx(0.44)
    assert poisson_binomial_upper_tail([0.2, 0.3], 2) == pytest.approx(0.06)


def test_binomial_sign_tail() -> None:
    assert binomial_upper_tail(3, 2, 0.5) == pytest.approx(0.5)
    assert binomial_upper_tail(3, 3, 0.5) == pytest.approx(0.125)


def test_holm_adjust_is_monotone_in_sorted_order() -> None:
    adjusted = holm_adjust({"a": 0.01, "b": 0.03, "c": 0.20})
    assert adjusted["a"] == pytest.approx(0.03)
    assert adjusted["b"] == pytest.approx(0.06)
    assert adjusted["c"] == pytest.approx(0.20)


def test_poisson_binomial_validates_inputs() -> None:
    with pytest.raises(ValueError):
        poisson_binomial_upper_tail([0.2, 1.2], 1)
    with pytest.raises(ValueError):
        poisson_binomial_upper_tail([0.2, 0.3], 3)
