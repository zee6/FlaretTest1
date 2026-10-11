import hashlib
import shutil
from pathlib import Path

import pytest

from football1.september_recovery_report import ARCHIVE, build_report

ROOT = Path(__file__).resolve().parents[1]


def test_original_evidence_scores_without_network_and_keeps_missing_lane_explicit():
    paths = [p for p in (ROOT / "prospective").rglob("*") if p.is_file()]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    report = build_report(ROOT)
    assert report["primary"]["prediction_records"] == report["primary"]["settled_records"] == 20
    assert report["recency_15d_only"]["settled_common_event_count"] == 10
    assert report["draw_possibility"]["settled_shadow_records"] == 10
    assert report["full_30d_vs_15d_comparison_available"] is False
    assert "recency_30d" in report["unavailable_files"]
    assert not any("30d" in key for key in report["recency_15d_only"]["models"])
    assert report["portfolio"]["official_research_portfolio"]["portfolio"]["bets_placed"] == 0
    top2 = report["draw_possibility"]["predeclared_rank_summaries"]["top_2_draw_possibility"]["events"]
    assert [(r["home"], r["away"]) for r in top2] == [("Bournemouth", "Brentford"), ("Leeds", "Newcastle")]
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


@pytest.mark.parametrize("name", ["draw_possibility.jsonl", "recency_15d.jsonl", "recovery_manifest.json"])
def test_rejects_changed_archive_bytes(tmp_path, name):
    shutil.copytree(ROOT / "prospective", tmp_path / "prospective")
    path = tmp_path / ARCHIVE / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_report(tmp_path)
