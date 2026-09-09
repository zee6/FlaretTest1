from __future__ import annotations

import json
from pathlib import Path

import pytest

from football1.portfolio_lab import PortfolioConfig
from football1.prospective import prediction_content_hash
from football1.prospective_portfolio_report import build_report
from football1.settlement import settlement_content_hash


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _prediction(
    event_id: str,
    record_id: str,
    date: str,
    market: dict[str, float],
    model: dict[str, float],
    odds: dict[str, float],
) -> dict:
    ev = {label: model[label] * odds[label] - 1.0 for label in ("home", "draw", "away")}
    max_ev = max(ev, key=ev.get)
    row = {
        "record_id": record_id,
        "event_id": event_id,
        "commence_time_utc": f"{date}T14:00:00Z",
        "features": {"season_start_year": 2026},
        "market_anchor": {"probability": market, "best_decimal_odds": odds},
        "model": {
            "probability": model,
            "max_predicted_ev_outcome": max_ev,
            "max_predicted_ev": ev[max_ev],
        },
    }
    row["content_sha256"] = prediction_content_hash(row)
    return row


def _settlement(prediction: dict, result: str) -> dict:
    row = {
        "settlement_id": f"s-{prediction['event_id']}",
        "prediction_record_id": prediction["record_id"],
        "prediction_content_sha256": prediction["content_sha256"],
        "event_id": prediction["event_id"],
        "result": result,
    }
    row["content_sha256"] = settlement_content_hash(row)
    return row


def test_official_portfolio_remains_unchanged_without_validated_rule(tmp_path: Path) -> None:
    p = _prediction(
        "e1",
        "p1",
        "2026-09-05",
        {"home": 0.50, "draw": 0.25, "away": 0.25},
        {"home": 0.55, "draw": 0.23, "away": 0.22},
        {"home": 2.10, "draw": 4.0, "away": 4.0},
    )
    ledger, settlements = tmp_path / "ledger.jsonl", tmp_path / "settlements.jsonl"
    _write(ledger, [p])
    _write(settlements, [_settlement(p, "home")])

    report = build_report(ledger, settlements, config=PortfolioConfig(starting_bankroll=1000, base_fraction=0.01))
    official = report["official_research_portfolio"]["portfolio"]
    assert official["bets_placed"] == 0
    assert official["final_bankroll"] == pytest.approx(1000.0)
    assert official["max_drawdown_fraction"] == pytest.approx(0.0)


def test_result_call_and_best_price_shadow_is_predeclared_structural_class(tmp_path: Path) -> None:
    p = _prediction(
        "e1",
        "p1",
        "2026-09-05",
        {"home": 0.50, "draw": 0.25, "away": 0.25},
        {"home": 0.55, "draw": 0.23, "away": 0.22},
        {"home": 2.10, "draw": 4.0, "away": 4.0},
    )
    ledger, settlements = tmp_path / "ledger.jsonl", tmp_path / "settlements.jsonl"
    _write(ledger, [p])
    _write(settlements, [_settlement(p, "home")])

    report = build_report(ledger, settlements)
    assert report["shadow_selection_counts"]["result_call_positive_price_interest"] == 1
    assert report["shadow_selection_counts"]["result_call_and_best_price_interest"] == 1
    flat = report["shadow_portfolios"]["result_call_and_best_price_interest"]["flat_stake"]
    assert flat["bets_placed"] == 1
    assert flat["pnl"] == pytest.approx(11.0)


def test_raw_max_ev_can_differ_from_result_call(tmp_path: Path) -> None:
    p = _prediction(
        "e1",
        "p1",
        "2026-09-05",
        {"home": 0.70, "draw": 0.20, "away": 0.10},
        {"home": 0.69, "draw": 0.20, "away": 0.11},
        {"home": 1.40, "draw": 5.0, "away": 11.0},
    )
    ledger, settlements = tmp_path / "ledger.jsonl", tmp_path / "settlements.jsonl"
    _write(ledger, [p])
    _write(settlements, [_settlement(p, "home")])

    report = build_report(ledger, settlements)
    assert report["shadow_selection_counts"]["result_call_positive_price_interest"] == 0
    assert report["shadow_selection_counts"]["raw_max_ev_every_settled_match"] == 1
    raw = report["shadow_portfolios"]["raw_max_ev_every_settled_match"]["flat_stake"]
    assert raw["journal"][0]["outcome"] == "away"
    assert raw["pnl"] == pytest.approx(-10.0)


def test_settlement_hash_link_must_match_prediction(tmp_path: Path) -> None:
    p = _prediction(
        "e1",
        "p1",
        "2026-09-05",
        {"home": 0.50, "draw": 0.25, "away": 0.25},
        {"home": 0.55, "draw": 0.23, "away": 0.22},
        {"home": 2.10, "draw": 4.0, "away": 4.0},
    )
    s = _settlement(p, "home")
    s["prediction_content_sha256"] = "wrong"
    s.pop("content_sha256")
    s["content_sha256"] = settlement_content_hash(s)
    ledger, settlements = tmp_path / "ledger.jsonl", tmp_path / "settlements.jsonl"
    _write(ledger, [p])
    _write(settlements, [s])

    with pytest.raises(ValueError, match="prediction hash mismatch"):
        build_report(ledger, settlements)
