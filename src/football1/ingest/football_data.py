from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://www.football-data.co.uk/mmz4281"
EPL_DIVISION = "E0"


def season_code(start_year: int) -> str:
    """Return Football-Data season code for a season starting in start_year."""
    if start_year < 1900 or start_year > 2098:
        raise ValueError("start_year must be between 1900 and 2098")
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def epl_csv_url(start_year: int) -> str:
    return f"{BASE_URL}/{season_code(start_year)}/{EPL_DIVISION}.csv"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_csv_bytes(data: bytes) -> None:
    if not data:
        raise ValueError("Downloaded file is empty")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Downloaded content is not UTF-8 CSV text") from exc
    reader = csv.reader(text.splitlines())
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("Downloaded CSV contains no header") from exc
    required = {"HomeTeam", "AwayTeam"}
    missing = required.difference(header)
    if missing:
        raise ValueError(
            "Downloaded content does not look like an EPL Football-Data CSV; "
            f"missing columns: {sorted(missing)}"
        )


def _download_bytes(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Football1Research/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def download_epl_season(
    start_year: int,
    output_dir: Path,
    *,
    force: bool = False,
    timeout: int = 30,
) -> Path:
    code = season_code(start_year)
    target = output_dir / f"EPL_{code}_E0.csv"
    if target.exists() and not force:
        raise FileExistsError(
            f"{target} already exists; raw data is immutable. Use --force only when replacement is intentional."
        )
    url = epl_csv_url(start_year)
    data = _download_bytes(url, timeout=timeout)
    _validate_csv_bytes(data)
    digest = _sha256(data)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    _atomic_write(target, data)
    _atomic_write(target.with_suffix(target.suffix + ".sha256"), f"{digest}  {target.name}\n".encode("utf-8"))
    metadata = {
        "competition": "English Premier League",
        "division_code": EPL_DIVISION,
        "season_start_year": start_year,
        "season_code": code,
        "source_url": url,
        "retrieved_at_utc": retrieved_at,
        "bytes": len(data),
        "sha256": digest,
    }
    _atomic_write(
        target.with_suffix(target.suffix + ".json"),
        (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download immutable EPL CSV files from Football-Data.co.uk.")
    parser.add_argument("--from-season", type=int, required=True)
    parser.add_argument("--to-season", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/football-data"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.from_season > args.to_season:
        raise SystemExit("--from-season must be <= --to-season")
    for start_year in range(args.from_season, args.to_season + 1):
        try:
            path = download_epl_season(
                start_year,
                args.output_dir,
                force=args.force,
                timeout=args.timeout,
            )
            print(f"downloaded {start_year}/{str(start_year + 1)[-2:]} -> {path}")
        except FileExistsError as exc:
            print(f"skipped: {exc}")


if __name__ == "__main__":
    main()
