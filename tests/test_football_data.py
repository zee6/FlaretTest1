from pathlib import Path

import pytest

from football1.ingest import football_data as fd


def test_season_code_current():
    assert fd.season_code(2026) == "2627"


def test_season_code_century_boundary():
    assert fd.season_code(1999) == "9900"


def test_epl_url():
    assert fd.epl_csv_url(2026) == "https://www.football-data.co.uk/mmz4281/2627/E0.csv"


def test_rejects_non_csv_payload():
    with pytest.raises(ValueError, match="missing columns"):
        fd._validate_csv_bytes(b"<html><body>error</body></html>")


def test_download_writes_raw_hash_and_metadata(monkeypatch, tmp_path: Path):
    payload = (
        b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
        b"E0,15/08/2026,Arsenal,Chelsea,2,1,H\n"
    )
    monkeypatch.setattr(fd, "_download_bytes", lambda url, timeout=30: payload)
    target = fd.download_epl_season(2026, tmp_path)
    assert target.read_bytes() == payload
    assert target.with_suffix(target.suffix + ".sha256").exists()
    assert target.with_suffix(target.suffix + ".json").exists()


def test_raw_file_is_not_overwritten_without_force(monkeypatch, tmp_path: Path):
    target = tmp_path / "EPL_2627_E0.csv"
    target.write_bytes(b"existing")
    monkeypatch.setattr(fd, "_download_bytes", lambda url, timeout=30: b"should-not-be-used")
    with pytest.raises(FileExistsError):
        fd.download_epl_season(2026, tmp_path)
