import copy
import json
from pathlib import Path

import pytest

from football1.mobile_results import FEED_PATH, build_feed, render_feed
from football1.prospective import prediction_content_hash
from football1.settlement import make_settlement_record, settlement_content_hash

ROOT = Path(__file__).resolve().parents[1]


def write_rows(root, name, rows):
    (root / f"prospective/{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.fixture
def sample(tmp_path):
    (tmp_path / "prospective").mkdir()
    # Frozen inputs only; synthetic outcomes never enter the production ledger.
    rows = [json.loads(line) for line in (ROOT / "prospective/ledger.jsonl").read_text().splitlines()]
    rows = [row for row in rows if row["snapshot_retrieved_at_utc"].startswith("2026-10-10")]
    write_rows(tmp_path, "ledger", rows)
    write_rows(tmp_path, "settlements", [])
    return tmp_path, rows


def settle(row, won=True):
    selection = row["model"]["max_predicted_ev_outcome"]
    outcome = selection if won else next(label for label in ("home", "draw", "away") if label != selection)
    home, away = {"home": (2, 0), "draw": (1, 1), "away": (0, 2)}[outcome]
    return make_settlement_record(row, {
        "id": row["event_id"], "completed": True,
        "home_team": row["home_team_provider"], "away_team": row["away_team_provider"],
        "scores": [{"name": row["home_team_provider"], "score": str(home)},
                   {"name": row["away_team_provider"], "score": str(away)}],
    }, scores_retrieved_at_utc="2026-10-13T12:00:00Z")


def rehash(row, prediction=False):
    unsigned = {k: v for k, v in row.items() if k != "content_sha256"}
    row["content_sha256"] = (prediction_content_hash if prediction else settlement_content_hash)(unsigned)


def test_committed_feed_is_current_and_retains_exact_forecasts():
    assert (ROOT / FEED_PATH).read_text() == render_feed(ROOT)
    feed = build_feed(ROOT)
    predictions = [json.loads(line) for line in (ROOT / "prospective/ledger.jsonl").read_text().splitlines()]
    source = {row["record_id"]: row for row in predictions}
    assert len(feed["batches"]) == len({p["snapshot_retrieved_at_utc"] for p in predictions})
    assert feed["official_policy"] == "no_validated_betting_rule"
    assert sum(len(batch["matches"]) for batch in feed["batches"]) == len(predictions)
    for batch in feed["batches"]:
        for match in batch["matches"]:
            assert match["model_probability"] == source[match["id"]]["model"]["probability"]
            assert match["prediction_sha256"] == source[match["id"]]["content_sha256"]


def test_no_results_are_unknown_not_zero_scores(sample):
    root, rows = sample
    batch = build_feed(root)["batches"][0]
    assert batch["settled_count"] == 0 and batch["pending_count"] == len(rows)
    assert all(value is None for value in batch["scoring"].values())
    assert batch["diagnostic"]["roi"] is None
    assert all(match["settlement"] is None for match in batch["matches"])


def test_partial_sample_winner_and_loser_pnl_and_roi(sample):
    root, rows = sample
    settlements = [settle(rows[0]), settle(rows[1], won=False)]
    write_rows(root, "settlements", settlements)
    batch = build_feed(root)["batches"][0]
    odds = rows[0]["market_anchor"]["best_decimal_odds"][rows[0]["model"]["max_predicted_ev_outcome"]]
    assert batch["settled_count"] == 2 and batch["pending_count"] == 7
    assert batch["diagnostic"]["stake_units"] == 2
    assert batch["diagnostic"]["pnl_units"] == pytest.approx(odds - 2)
    assert batch["diagnostic"]["roi"] == pytest.approx((odds - 2) / 2)
    assert batch["diagnostic"]["wins"] == 1
    assert batch["scoring"]["model_log_loss"] == pytest.approx(sum(s["model_log_loss"] for s in settlements) / 2)
    # Source order cannot change metrics or the display order.
    write_rows(root, "ledger", list(reversed(rows)))
    write_rows(root, "settlements", list(reversed(settlements)))
    assert build_feed(root)["batches"][0] == batch


def test_losses_and_drawdown_include_starting_zero(sample):
    root, rows = sample
    write_rows(root, "settlements", [settle(row, won=False) for row in rows])
    diagnostic = build_feed(root)["batches"][0]["diagnostic"]
    assert diagnostic == {"stake_units": 9, "pnl_units": -9, "roi": -1, "wins": 0, "max_drawdown_units": 9}


def test_simultaneous_kickoffs_are_grouped_for_drawdown(sample):
    root, rows = sample
    rows = copy.deepcopy(rows[:2])
    rows[1]["commence_time_utc"] = rows[0]["commence_time_utc"]
    rehash(rows[1], prediction=True)
    write_rows(root, "ledger", rows)
    write_rows(root, "settlements", [settle(rows[0]), settle(rows[1], won=False)])
    diagnostic = build_feed(root)["batches"][0]["diagnostic"]
    assert diagnostic["max_drawdown_units"] == max(0, -diagnostic["pnl_units"])


@pytest.mark.parametrize("kind", ["duplicate", "unknown", "wrong_hash", "score", "pnl", "time"])
def test_rejects_corrupt_settlements_even_when_rehashed(sample, kind):
    root, rows = sample
    result = settle(rows[0])
    if kind == "unknown": result["prediction_record_id"] = "unknown"
    if kind == "wrong_hash": result["prediction_content_sha256"] = "wrong"
    if kind == "score": result["home_score"] = -1
    if kind == "pnl": result["recorded_max_ev_selection_unit_pnl"] += 1
    if kind == "time": result["scores_retrieved_at_utc"] = "2026-10-01T12:00:00Z"
    rehash(result)
    write_rows(root, "settlements", [result, result] if kind == "duplicate" else [result])
    with pytest.raises(ValueError): build_feed(root)


@pytest.mark.parametrize("kind", ["late", "probability", "odds", "selection", "active_policy", "duplicate"])
def test_rejects_invalid_prediction_contract(sample, kind):
    root, rows = sample
    row = rows[0]
    if kind == "late": row["snapshot_retrieved_at_utc"] = row["commence_time_utc"]
    if kind == "probability": row["model"]["probability"]["home"] = 0.99
    if kind == "odds": row["market_anchor"]["best_decimal_odds"]["home"] = 1
    if kind == "selection": row["model"]["max_predicted_ev"] += 0.1
    if kind == "active_policy": row["model"]["strategy_threshold"] = 0.05
    if kind == "duplicate": rows.append(copy.deepcopy(row))
    rehash(row, prediction=True)
    write_rows(root, "ledger", rows)
    with pytest.raises(ValueError): build_feed(root)


def test_missing_ledger_is_not_a_valid_empty_feed(sample):
    root, _ = sample
    (root / "prospective/settlements.jsonl").unlink()
    with pytest.raises(FileNotFoundError): build_feed(root)
