"""Reproduce available September evidence without substituting missing originals."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from football1.draw_possibility_prospective_report import build_report as draw_report
from football1.prospective import prediction_content_hash
from football1.prospective_error_anatomy import build_report as error_report
from football1.prospective_error_batch_comparison import build_report as batch_report
from football1.prospective_portfolio_report import build_report as portfolio_report
from football1.prospective_report import build_report as primary_report
from football1.recency_prospective_report import build_report as recency_report

ARCHIVE = Path("prospective/shadows/2026-09-12-14")
MANIFEST_SHA256 = "eacca17120e71f085564cb847ee0ac306829ae2650e39f68fe4dc5f2c0c8e71a"


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_report(root: Path) -> dict[str, Any]:
    """Score the original first 20 predictions, with an explicit missing 30d lane."""
    raw = (root / ARCHIVE / "recovery_manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Recovery manifest hash mismatch")
    manifest = json.loads(raw)
    wanted = manifest["prediction_content_sha256_by_id"]
    predictions = [r for r in _rows(root / "prospective/ledger.jsonl") if r["record_id"] in wanted]
    if len(predictions) != 20 or len({r["record_id"] for r in predictions}) != 20:
        raise ValueError("Expected exactly the original 20 September predictions")
    for row in predictions:
        unsigned = dict(row)
        stored = unsigned.pop("content_sha256")
        if stored != wanted[row["record_id"]] or stored != prediction_content_hash(unsigned):
            raise ValueError("Original September prediction hash mismatch")
    paths = {}
    source_sets = []
    for name, spec in manifest["recovered_files"].items():
        path = root / spec["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != spec["sha256"]:
            raise ValueError(f"Original {name} file hash mismatch")
        rows = _rows(path)
        sources = {r["source_prediction"]["record_id"] for r in rows}
        if len(rows) != 10 or len(sources) != 10 or not sources <= wanted.keys():
            raise ValueError("Recovered shadow source sample mismatch")
        source_sets.append(sources)
        paths[name] = path
    if source_sets[0] != source_sets[1]:
        raise ValueError("Recovered shadows must share the same ten predictions")
    settlements = [r for r in _rows(root / "prospective/settlements.jsonl") if r["prediction_record_id"] in wanted]
    with TemporaryDirectory() as directory:
        ledger, results = Path(directory) / "ledger.jsonl", Path(directory) / "settlements.jsonl"
        for path, rows in ((ledger, predictions), (results, settlements)):
            path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        report = {
            "status": "partial_archive_recovery",
            "manifest_sha256": MANIFEST_SHA256,
            "decision_weight": 0.0,
            "scope": manifest["evaluation_scope"],
            "unavailable_files": manifest["unavailable_files"],
            "full_30d_vs_15d_comparison_available": False,
            "primary": primary_report(ledger, results),
            "recency_15d_only": recency_report(ledger, results, [paths["recency_15d"]]),
            "draw_possibility": draw_report(paths["draw_possibility"], ledger, results),
            "error_anatomy": error_report(ledger, results),
            "error_batches": batch_report(ledger, results),
            "portfolio": portfolio_report(ledger, results),
        }
    report["recency_15d_only"]["shadow_files"][0]["path"] = manifest["recovered_files"]["recency_15d"]["path"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.repository_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "predictions": report["primary"]["prediction_records"],
                      "settled": report["primary"]["settled_records"],
                      "full_30d_vs_15d_comparison_available": False}))


if __name__ == "__main__":
    main()
