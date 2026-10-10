"""Synthetic outcomes exercise the frozen sample; these are not real settlements."""
import copy
import hashlib
import json
import math
import shutil
from pathlib import Path

import pytest

from football1.october_slate_report import SLATE_PATH, build_report
from football1.prospective import prediction_content_hash
from football1.settlement import make_settlement_record, settlement_content_hash

ROOT = Path(__file__).resolve().parents[1]


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


@pytest.fixture
def evidence(tmp_path):
    shutil.copytree(ROOT / "prospective", tmp_path / "prospective")
    manifest = json.loads((tmp_path / SLATE_PATH / "manifest.json").read_text())
    wanted = set(manifest["prediction_record_ids"])
    predictions = [json.loads(line) for line in (tmp_path / "prospective/ledger.jsonl").read_text().splitlines()]
    selected = [row for row in predictions if row["record_id"] in wanted]
    # Isolate the real locked inputs from any later production settlements.
    write_rows(tmp_path / "prospective/settlements.jsonl", [])
    return tmp_path, selected


def synthetic_settlement(prediction, index=0):
    home, away = ((2, 0), (1, 1), (0, 3))[index % 3]
    return make_settlement_record(prediction, {
        "id": prediction["event_id"], "completed": True,
        "home_team": prediction["home_team_provider"],
        "away_team": prediction["away_team_provider"],
        "scores": [{"name": prediction["home_team_provider"], "score": str(home)},
                   {"name": prediction["away_team_provider"], "score": str(away)}],
    }, scores_retrieved_at_utc="2026-10-13T12:00:00Z")


@pytest.mark.parametrize("count,stage", [(0, "prospective_frozen"), (3, "prospective_partial"), (9, "prospective_complete")])
def test_stages_common_sample_and_independent_accounting(evidence, count, stage):
    root, predictions = evidence
    rows = [synthetic_settlement(row, i) for i, row in enumerate(predictions[:count])]
    write_rows(root / "prospective/settlements.jsonl", rows)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "prospective").rglob("*") if p.is_file()}
    report = build_report(root)
    assert report["stage"] == stage
    assert report["prediction_records"] == 9
    assert report["settled_records"] == report["recency"]["settled_common_event_count"] == count
    assert report["unsettled_records"] == 9 - count
    assert report["draw_possibility"]["status"] == "unavailable_at_freeze"
    assert report["portfolio"]["official_research_portfolio"]["portfolio"]["bets_placed"] == 0
    expected = None if count == 0 else sum(-math.log(p["model"]["probability"][s["result"]]) for p, s in zip(predictions, rows)) / count
    assert report["primary"]["probability_scoring"]["model_mean_log_loss"] == pytest.approx(expected)
    for p, s in zip(predictions, rows):
        for label in ("home", "draw", "away"):
            expected_pnl = p["market_anchor"]["best_decimal_odds"][label] - 1 if label == s["result"] else -1
            assert s["unit_pnl_if_bet_at_recorded_best_odds"][label] == pytest.approx(expected_pnl)
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}


@pytest.mark.parametrize("kind", ["manifest", "shadow", "prediction", "missing_prediction", "duplicate_prediction"])
def test_rejects_changed_or_incomplete_frozen_evidence(evidence, kind):
    root, predictions = evidence
    if kind in ("manifest", "shadow"):
        name = "manifest.json" if kind == "manifest" else "recency_15d.jsonl"
        path = root / SLATE_PATH / name
        path.write_text(path.read_text() + "\n")
    else:
        rows = copy.deepcopy(predictions)
        if kind == "prediction":
            rows[0]["model"]["probability"]["home"] += 0.01
            unsigned = dict(rows[0])
            unsigned.pop("content_sha256")
            rows[0]["content_sha256"] = prediction_content_hash(unsigned)
        elif kind == "missing_prediction":
            rows.pop()
        else:
            rows[-1] = rows[0]
        write_rows(root / "prospective/ledger.jsonl", rows)
    with pytest.raises(ValueError):
        build_report(root)


@pytest.mark.parametrize("kind", ["duplicate", "result", "pnl", "score", "timestamp", "event", "probability_score"])
def test_rejects_semantically_corrupt_even_rehashed_settlements(evidence, kind):
    root, predictions = evidence
    row = synthetic_settlement(predictions[0])
    if kind == "result":
        row["result"] = "draw"
    elif kind == "pnl":
        row["unit_pnl_if_bet_at_recorded_best_odds"]["away"] = 1.0
    elif kind == "score":
        row["home_score"] = -1
    elif kind == "timestamp":
        row["scores_retrieved_at_utc"] = "2026-10-09T12:00:00Z"
    elif kind == "event":
        row["event_id"] = "different-event"
    elif kind == "probability_score":
        row["model_brier"] += 0.01
    unsigned = dict(row)
    unsigned.pop("content_sha256")
    row["content_sha256"] = settlement_content_hash(unsigned)
    write_rows(root / "prospective/settlements.jsonl", [row, row] if kind == "duplicate" else [row])
    with pytest.raises(ValueError):
        build_report(root)


def test_other_batches_and_later_snapshots_cannot_enter_sample(evidence):
    root, predictions = evidence
    expected = build_report(root)
    later = copy.deepcopy(predictions[0])
    later["record_id"] = "later-snapshot-same-event"
    later["snapshot_retrieved_at_utc"] = "2026-10-10T12:30:00Z"
    unsigned = dict(later)
    unsigned.pop("content_sha256")
    later["content_sha256"] = prediction_content_hash(unsigned)
    path = root / "prospective/ledger.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    write_rows(path, list(reversed(rows + [later])))
    other = next(row for row in rows if row["commence_time_utc"][:7] == "2026-09")
    write_rows(root / "prospective/settlements.jsonl", [synthetic_settlement(later), synthetic_settlement(other)])
    assert build_report(root) == expected
