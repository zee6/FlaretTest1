from pathlib import Path

import pytest

from football1.build_db import discover_season_files, season_start_year_from_code


def test_inverse_season_code():
    assert season_start_year_from_code("2627") == 2026
    assert season_start_year_from_code("9900") == 1999


def test_rejects_bad_season_code():
    with pytest.raises(ValueError, match="Non-consecutive"):
        season_start_year_from_code("2628")


def test_discovers_only_expected_epl_files(tmp_path: Path):
    (tmp_path / "EPL_2526_E0.csv").write_text("x", encoding="utf-8")
    (tmp_path / "EPL_2627_E0.csv").write_text("x", encoding="utf-8")
    (tmp_path / "README.txt").write_text("x", encoding="utf-8")
    assert discover_season_files(tmp_path) == [
        (2025, tmp_path / "EPL_2526_E0.csv"),
        (2026, tmp_path / "EPL_2627_E0.csv"),
    ]
