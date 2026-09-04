from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from football1.elo_observer import (
    CONFIDENCE_BANDS,
    ODDS_BANDS,
    _band_name,
    _summarize,
    build_elo_observer_report,
)


def _db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE matches (
                match_id TEXT PRIMARY KEY,
                season_start_year INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                ftr TEXT NOT NULL,
                raw_json TEXT NOT NULL
            )
            """
        )
        fixtures = (
            ("Alpha", "Bravo"),
            ("Charlie", "Delta"),
            ("Alpha", "Charlie"),
            ("Bravo", "Delta"),
            ("Alpha", "Delta"),
            ("Bravo", "Charlie"),
        )
        outcomes = ("H", "D", "A", "H", "D", "A")
        for season in (2022, 2023, 2024, 2025):
            for i, ((home, away), result) in enumerate(zip(fixtures, outcomes), start=1):
                raw = json.dumps({"B365H": "1.80", "B365D": "3.50", "B365A": "4.50"})
                conn.execute(
                    "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"{season}-{i}", season, f"{season}-08-{9+i:02d}", home, away, result, raw),
                )
        conn.commit()
    finally:
        conn.close()
    return path


def test_fixed_band_boundaries() -> None:
    assert _band_name(0.399, CONFIDENCE_BANDS) == "under_40pct"
    assert _band_name(0.40, CONFIDENCE_BANDS) == "40_to_50pct"
    assert _band_name(1.49, ODDS_BANDS) == "under_1_50"
    assert _band_name(1.50, ODDS_BANDS) == "1_50_to_2_00"
    assert _band_name(5.00, ODDS_BANDS) == "5_00_plus"


def test_summary_reports_hits_and_blind_flat_stake() -> None:
    picks = [
        {
            "correct": True,
            "elo_top_probability": 0.60,
            "b365_decimal_odds": 2.0,
            "flat_stake_profit_units": 1.0,
        },
        {
            "correct": False,
            "elo_top_probability": 0.55,
            "b365_decimal_odds": 3.0,
            "flat_stake_profit_units": -1.0,
        },
    ]
    s = _summarize(picks)
    assert s["picks"] == 2
    assert s["correct"] == 1
    assert s["incorrect"] == 1
    assert s["hit_rate"] == pytest.approx(0.5)
    assert s["blind_flat_stake_b365"]["profit_units"] == pytest.approx(0.0)
    assert s["blind_flat_stake_b365"]["roi"] == pytest.approx(0.0)


def test_walk_forward_observer_report_is_oos_and_grouped(tmp_path: Path) -> None:
    db = _db(tmp_path / "observer.sqlite")
    report = build_elo_observer_report(db, min_train_seasons=3)

    overall = report["overall"]
    assert overall["picks"] == 6
    assert overall["correct"] + overall["incorrect"] == 6
    assert overall["blind_flat_stake_b365"]["bets"] == 6
    assert sum(x["picks"] for x in report["by_predicted_outcome"].values()) == 6
    assert sum(x["picks"] for x in report["by_elo_confidence"].values()) == 6
    assert sum(x["picks"] for x in report["by_b365_odds_for_elo_pick"].values()) == 6
    assert len(report["latest_predictions"]) == 6

    for row in report["latest_predictions"]:
        assert row["season_start_year"] == 2025
        assert row["b365_decimal_odds"] is not None
        assert row["market_top_pick"] in {"H", "D", "A"}
        assert row["elo_price_ev"] is not None
