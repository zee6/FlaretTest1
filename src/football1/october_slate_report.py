"""Score registered immutable October slates using the existing scorers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from football1.prospective import prediction_content_hash
from football1.prospective_error_anatomy import build_report as error_report
from football1.prospective_portfolio_report import build_report as portfolio_report
from football1.prospective_report import build_report as primary_report
from football1.recency_prospective_report import build_report as recency_report
from football1.evidence_validation import (
    _require, _time, verify_settlement_against_prediction as _verify_settlement,
)

SLATE_PATH = Path("prospective/shadows/2026-10-10-12")
# Bytes committed before kickoff; do not update to accommodate changed evidence.
MANIFEST_SHA256 = "071490a0eeec925f0e3d1d276f9d2269141ec8ed73fc88d31c534732323b7850"
SLATES = {
    "2026-10-10-12": (SLATE_PATH, MANIFEST_SHA256, 9),
    "2026-10-17-19": (
        Path("prospective/shadows/2026-10-17-19"),
        "7772fe8e28d2549be76054effcbdb5ef593129aefcfabf8122324256ab78f609",
        10,
    ),
}


def _read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _unit_diagnostic(predictions: dict[str, dict[str, Any]], settlements: list[dict[str, Any]]) -> dict[str, Any]:
    """Existing max-EV-every-match observer, gross one-unit stakes, no threshold."""
    by_kickoff: dict[str, float] = {}
    matches = []
    for result in settlements:
        prediction = predictions[result["prediction_record_id"]]
        selection = prediction["model"]["max_predicted_ev_outcome"]
        odds = prediction["market_anchor"]["best_decimal_odds"][selection]
        won = selection == result["result"]
        pnl = odds - 1 if won else -1.0
        kickoff = _time(prediction["commence_time_utc"]).isoformat()
        by_kickoff[kickoff] = by_kickoff.get(kickoff, 0.0) + pnl
        matches.append({
            "prediction_record_id": prediction["record_id"],
            "kickoff_utc": prediction["commence_time_utc"],
            "home": prediction["home_team_provider"], "away": prediction["away_team_provider"],
            "home_score": result["home_score"], "away_score": result["away_score"],
            "selection": selection, "decimal_odds": odds,
            "recorded_predicted_ev": prediction["model"]["max_predicted_ev"],
            "won": won, "pnl_units": pnl,
        })
    equity = peak = drawdown = 0.0
    for kickoff in sorted(by_kickoff):
        equity += by_kickoff[kickoff]
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    count = len(matches)
    wins = sum(row["won"] for row in matches)
    return {
        "definition": "one_unit_on_recorded_max_ev_outcome_every_settled_match_including_negative_ev",
        "status": "hypothetical_gross_quoted_prices_zero_decision_weight",
        "stake_units": count, "pnl_units": equity, "roi": equity / count if count else None,
        "wins": wins, "losses": count - wins, "max_drawdown_units": drawdown,
        "drawdown_order": "kickoff_utc_with_simultaneous_kickoffs_grouped",
        "matches": sorted(matches, key=lambda row: (row["kickoff_utc"], row["prediction_record_id"])),
    }


def build_report(repository_root: Path, *, slate: str = "2026-10-10-12") -> dict[str, Any]:
    """Validate committed October evidence and score its exact settlement subset.

    No network, fitting, prediction generation, or writes to source evidence occur.
    Other batches and later snapshots cannot enter this sample.
    """
    if slate not in SLATES:
        raise ValueError(f"Unknown registered frozen slate: {slate}")
    slate_path, manifest_sha256, sample_size = SLATES[slate]
    manifest_path = repository_root / slate_path / "manifest.json"
    raw = manifest_path.read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == manifest_sha256, "Frozen manifest hash mismatch")
    manifest = json.loads(raw)
    wanted = dict(zip(manifest["prediction_record_ids"], manifest["prediction_content_sha256"], strict=True))
    predictions = [row for row in _read_rows(repository_root / "prospective/ledger.jsonl")
                   if row["record_id"] in wanted]
    _require(len(predictions) == len(wanted) == sample_size, "Frozen prediction sample size mismatch")
    _require(len({row["record_id"] for row in predictions}) == sample_size, "Duplicate frozen prediction")
    _require(len({row["event_id"] for row in predictions}) == sample_size, "Duplicate frozen event")
    by_id = {row["record_id"]: row for row in predictions}
    for row in predictions:
        unsigned = dict(row)
        stored = unsigned.pop("content_sha256", None)
        _require(stored == wanted[row["record_id"]] == prediction_content_hash(unsigned),
                 "Frozen prediction hash mismatch")
        _require(row["snapshot_retrieved_at_utc"] == manifest["snapshot_retrieved_at_utc"],
                 "Prediction snapshot mismatch")
        _require(_time(row["snapshot_retrieved_at_utc"]) < _time(row["commence_time_utc"]),
                 "Prediction must precede kickoff")
    predictions.sort(key=lambda row: (row["commence_time_utc"], row["record_id"]))
    shadows = []
    for name in ("recency_30d", "recency_15d"):
        spec = manifest["shadow_files"][name]
        path = repository_root / spec["path"]
        _require(hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"],
                 f"Frozen {name} file hash mismatch")
        rows = _read_rows(path)
        _require(len(rows) == sample_size and {row["source_prediction"]["record_id"] for row in rows} == set(wanted),
                 "Shadow sample differs from frozen primary sample")
        for row in rows:
            source = by_id[row["source_prediction"]["record_id"]]
            kickoff = _time(source["commence_time_utc"])
            _require(_time(row["commence_time_utc"]) == kickoff, "Shadow kickoff mismatch")
            _require(_time(source["snapshot_retrieved_at_utc"]) <= _time(row["shadow_locked_at_utc"]) < kickoff,
                     "Shadow lock must follow snapshot and precede kickoff")
        shadows.append(path)
    settlements = [row for row in _read_rows(repository_root / "prospective/settlements.jsonl")
                   if row["prediction_record_id"] in wanted]
    _require(len({row["prediction_record_id"] for row in settlements}) == len(settlements),
             "Duplicate slate settlement")
    for row in settlements:
        _verify_settlement(row, by_id[row["prediction_record_id"]])
    settlements.sort(key=lambda row: row["prediction_record_id"])
    with TemporaryDirectory() as directory:
        ledger, results = Path(directory) / "ledger.jsonl", Path(directory) / "settlements.jsonl"
        for path, rows in ((ledger, predictions), (results, settlements)):
            path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
        primary = primary_report(ledger, results)
        recency = recency_report(ledger, results, shadows)
        errors = error_report(ledger, results)
        portfolio = portfolio_report(ledger, results)
    # Keep portable report paths rather than machine-specific checkout paths.
    for metadata, name in zip(recency["shadow_files"], ("recency_30d", "recency_15d"), strict=True):
        metadata["path"] = manifest["shadow_files"][name]["path"]
    settled = len(settlements)
    _require(primary["settled_records"] == recency["settled_common_event_count"] ==
             errors["settled_matches"] == portfolio["settled_records"] == settled,
             "Scorers disagree on settlement sample")
    _require(portfolio["official_research_portfolio"]["portfolio"]["bets_placed"] == 0,
             "Official portfolio must remain inactive")
    return {
        "slate": manifest["slate"],
        "stage": "prospective_frozen" if settled == 0 else "prospective_complete" if settled == sample_size else "prospective_partial",
        "manifest_sha256": manifest_sha256,
        "scope": manifest["scope"],
        "prediction_records": sample_size,
        "settled_records": settled,
        "unsettled_records": sample_size - settled,
        "decision_weight": 0.0,
        "draw_possibility": {"status": "unavailable_at_freeze", "reason": manifest["missing_shadows"]["draw_possibility"]},
        "prohibited": manifest.get("prohibited", [
            "No forecast refit, changed reference, betting threshold or decision weight from inspected results.",
            "No other slate or later snapshot may enter this sample.",
        ]),
        "primary": primary,
        "recency": recency,
        "error_anatomy": errors,
        "portfolio": portfolio,
        "unit_max_ev_diagnostic": _unit_diagnostic(by_id, settlements),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--slate", choices=sorted(SLATES), default="2026-10-10-12")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.repository_root, slate=args.slate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: report[key] for key in ("slate", "stage", "prediction_records", "settled_records", "unsettled_records")}))


if __name__ == "__main__":
    main()
