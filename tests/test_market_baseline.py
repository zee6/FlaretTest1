import json
import math
import sqlite3
from pathlib import Path

import pytest

from football1.market_baseline import (
    devig_decimal_odds,
    evaluate_market_baseline,
    odds_columns,
    score_probabilities,
)


def test_odds_columns_keep_preclosing_and_closing_distinct():
    assert odds_columns("B365", "pre_closing") == ("B365H", "B365D", "B365A")
    assert odds_columns("B365", "closing") == ("B365CH", "B365CD", "B365CA")


def test_devig_decimal_odds_normalizes_implied_probabilities():
    probs, overround = devig_decimal_odds((2.0, 4.0, 4.0))
    assert overround == pytest.approx(1.0)
    assert probs == pytest.approx((0.5, 0.25, 0.25))
    assert sum(probs) == pytest.approx(1.0)


def test_scoring_uses_realized_result_only_for_evaluation():
    probs = (0.5, 0.3, 0.2)
    scores = score_probabilities(probs, "H")
    assert scores.log_loss == pytest.approx(-math.log(0.5))
    assert scores.brier == pytest.approx((0.5 - 1.0) ** 2 + 0.3**2 + 0.2**2)
    assert scores.correct == 1


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE matches (
                match_id TEXT PRIMARY KEY,
                season_start_year INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                ftr TEXT NOT NULL,
                raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?)",
            (
                "m1",
                2025,
                "2025-08-01",
                "H",
                json.dumps({"B365H": "2.0", "B365D": "4.0", "B365A": "4.0"}),
            ),
        )
        conn.execute(
            "INSERT INTO matches VALUES (?, ?, ?, ?, ?)",
            (
                "m2",
                2025,
                "2025-08-02",
                "A",
                json.dumps({"B365H": "", "B365D": "", "B365A": ""}),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_market_baseline_reports_coverage_and_scores(tmp_path: Path):
    db = tmp_path / "test.sqlite"
    _make_db(db)
    report = evaluate_market_baseline(db, "B365", "pre_closing")
    assert report["total_matches"] == 2
    assert report["usable_matches"] == 1
    assert report["coverage"] == pytest.approx(0.5)
    assert report["log_loss"] == pytest.approx(-math.log(0.5))
    assert report["accuracy"] == pytest.approx(1.0)
