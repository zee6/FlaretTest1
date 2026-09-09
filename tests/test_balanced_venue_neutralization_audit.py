from __future__ import annotations

import pytest

from football1.balanced_venue_neutralization_audit import _group_summary, _threshold_report


def _row(gap: float, elo_diff: float, result: str) -> dict:
    return {
        "season_start_year": 2025,
        "match_id": f"{gap}-{elo_diff}-{result}",
        "result": result,
        "probability": {"home": 0.36, "draw": 0.28, "away": 0.36},
        "odds": {"home": 2.8, "draw": 3.5, "away": 2.8},
        "home_away_gap": gap,
        "elo_diff": elo_diff,
        "strength_group": "away_elo_stronger" if elo_diff < 0 else "home_elo_at_least_as_strong",
    }


def test_group_summary_reports_mean_raw_elo_diff() -> None:
    result = _group_summary([_row(0.01, -30.0, "draw"), _row(0.02, -10.0, "home")])
    assert result["matches"] == 2
    assert result["mean_raw_elo_diff_home_minus_away"] == pytest.approx(-20.0)


def test_threshold_report_uses_elo_sign_only() -> None:
    rows = [
        _row(0.01, -1.0, "draw"),
        _row(0.03, 0.0, "home"),
        _row(0.04, 25.0, "away"),
        _row(0.20, -50.0, "draw"),
    ]
    report = _threshold_report(rows, 0.05)
    assert report["matches"] == 3
    assert report["groups"]["away_elo_stronger"]["matches"] == 1
    assert report["groups"]["home_elo_at_least_as_strong"]["matches"] == 2
    assert report["away_elo_stronger_share"] == pytest.approx(1 / 3)


def test_empty_group_is_explicit() -> None:
    report = _threshold_report([_row(0.01, 10.0, "home")], 0.02)
    away = report["groups"]["away_elo_stronger"]
    assert away["matches"] == 0
    assert away["mean_raw_elo_diff_home_minus_away"] is None
    assert away["outcomes"]["draw"]["actual_frequency"] is None
