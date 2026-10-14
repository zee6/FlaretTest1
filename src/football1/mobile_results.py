"""Export an offline-validated, deterministic results feed for the iPhone UI."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from football1.evidence_validation import _require, _time, verify_settlement_against_prediction
from football1.prospective import _odds_tuple, _probability_tuple
from football1.prospective_report import _verify_predictions, _verify_settlements

LABELS = ("home", "draw", "away")
FEED_PATH = Path("prospective/mobile_results.json")


def build_feed(repository_root: Path) -> dict[str, Any]:
    """Read the complete ledgers; reject missing, corrupt or inconsistent evidence.

    Batches are separate snapshot samples. A later lock never replaces an earlier
    prediction, and unresolved results never count as losses or probability scores.
    This exports the existing max-EV-every-match diagnostic, not a new strategy.
    """
    paths = [repository_root / f"prospective/{name}.jsonl" for name in ("ledger", "settlements")]
    raw = [path.read_bytes() for path in paths]  # A missing file is not an empty sample.
    predictions, settlements = [[json.loads(line) for line in data.splitlines() if line.strip()] for data in raw]
    _verify_predictions(predictions)
    _verify_settlements(settlements)
    by_id = {row["record_id"]: row for row in predictions}
    settled_by_id = {row["prediction_record_id"]: row for row in settlements}
    batches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_events: set[tuple[str, str]] = set()
    for prediction in predictions:
        snapshot = prediction["snapshot_retrieved_at_utc"]
        _require(prediction["status"] == "prediction_locked", "Prediction must be locked")
        _require(_time(snapshot) < _time(prediction["commence_time_utc"]), "Prediction must precede kickoff")
        event_key = (snapshot, prediction["event_id"])
        _require(event_key not in seen_events, "Duplicate event within snapshot")
        seen_events.add(event_key)
        model = prediction["model"]
        market = prediction["market_anchor"]
        for source in (model, market):
            _probability_tuple(source["probability"])
        _odds_tuple(market["best_decimal_odds"])
        # Future policy activation requires a new, explicit UI contract.
        _require(model["strategy_threshold"] is None, "Mobile results require the inactive official policy")
        ev = {label: model["probability"][label] * market["best_decimal_odds"][label] - 1 for label in LABELS}
        selected = model["max_predicted_ev_outcome"]
        _require(selected in LABELS and math.isclose(ev[selected], max(ev.values()), abs_tol=1e-10),
                 "Recorded max-EV selection is inconsistent")
        _require(math.isclose(model["max_predicted_ev"], ev[selected], abs_tol=1e-10), "Recorded EV mismatch")
        batches[snapshot].append(prediction)
    for settlement in settlements:
        prediction = by_id.get(settlement["prediction_record_id"])
        _require(prediction is not None, "Settlement references unknown prediction")
        verify_settlement_against_prediction(settlement, prediction)

    exported = []
    for snapshot in sorted(batches, key=_time, reverse=True):
        rows = sorted(batches[snapshot], key=lambda row: (_time(row["commence_time_utc"]), row["record_id"]))
        resolved = [settled_by_id[row["record_id"]] for row in rows if row["record_id"] in settled_by_id]
        count = len(resolved)
        pnl = sum(row["recorded_max_ev_selection_unit_pnl"] for row in resolved)
        # Aggregate simultaneous kickoffs before measuring drawdown: arbitrary
        # ordering of matches at one kickoff must not manufacture an equity path.
        by_kickoff: dict[str, float] = defaultdict(float)
        matches = []
        for row in rows:
            result = settled_by_id.get(row["record_id"])
            if result:
                by_kickoff[_time(row["commence_time_utc"]).isoformat()] += result["recorded_max_ev_selection_unit_pnl"]
            matches.append({
                "id": row["record_id"], "prediction_sha256": row["content_sha256"],
                "home": row["home_team_provider"], "away": row["away_team_provider"],
                "kickoff_utc": row["commence_time_utc"],
                "model_probability": row["model"]["probability"],
                "market_probability": row["market_anchor"]["probability"],
                "odds": row["market_anchor"]["best_decimal_odds"],
                "selection": row["model"]["max_predicted_ev_outcome"],
                "predicted_ev": row["model"]["max_predicted_ev"],
                "settlement": None if result is None else {
                    "home_score": result["home_score"], "away_score": result["away_score"],
                    "outcome": result["result"],
                    "pnl_units": result["recorded_max_ev_selection_unit_pnl"],
                    "recorded_at_utc": result["scores_retrieved_at_utc"],
                },
            })
        equity = peak = drawdown = 0.0
        for kickoff in sorted(by_kickoff):
            equity += by_kickoff[kickoff]
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
        dates = [_time(row["commence_time_utc"]).date().isoformat() for row in rows]
        exported.append({
            "id": snapshot, "frozen_at_utc": snapshot,
            "start_date": min(dates), "end_date": max(dates),
            "settled_count": count, "pending_count": len(rows) - count,
            "scoring": {key: sum(row[key] for row in resolved) / count if count else None
                        for key in ("model_log_loss", "market_log_loss", "model_brier", "market_brier")},
            "diagnostic": {
                "stake_units": count, "pnl_units": pnl, "roi": pnl / count if count else None,
                "wins": sum(row["recorded_max_ev_outcome"] == row["result"] for row in resolved),
                "max_drawdown_units": drawdown,
            },
            "matches": matches,
        })
    return {
        "schema_version": 1,
        "source_sha256": {path.name: hashlib.sha256(data).hexdigest() for path, data in zip(paths, raw, strict=True)},
        "last_settlement_at_utc": max((row["scores_retrieved_at_utc"] for row in settlements), key=_time, default=None),
        "official_policy": "no_validated_betting_rule",
        "batches": exported,
    }


def render_feed(repository_root: Path) -> str:
    return json.dumps(build_feed(repository_root), indent=2, sort_keys=True, allow_nan=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--check", action="store_true", help="Fail if the committed feed is stale")
    args = parser.parse_args()
    path = args.repository_root / FEED_PATH
    content = render_feed(args.repository_root)
    if args.check:
        if not path.exists() or path.read_text() != content:
            raise SystemExit("Mobile results feed is stale; run python -m football1.mobile_results")
        print("Mobile results feed matches validated ledgers")
    else:
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
