from __future__ import annotations

import argparse
import re
from pathlib import Path

from football1.canonical import build_database


EPL_FILENAME_RE = re.compile(r"^EPL_(\d{4})_E0\.csv$")


def season_start_year_from_code(code: str) -> int:
    if not re.fullmatch(r"\d{4}", code):
        raise ValueError(f"Invalid season code: {code!r}")
    start = int(code[:2])
    end = int(code[2:])
    if end != (start + 1) % 100:
        raise ValueError(f"Non-consecutive season code: {code!r}")
    return 1900 + start if start >= 90 else 2000 + start


def discover_season_files(input_dir: Path) -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in sorted(input_dir.glob("EPL_*_E0.csv")):
        match = EPL_FILENAME_RE.match(path.name)
        if not match:
            continue
        found.append((season_start_year_from_code(match.group(1)), path))
    if not found:
        raise FileNotFoundError(f"No EPL raw CSV files found in {input_dir}")
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the canonical Football 1 SQLite database from downloaded EPL CSVs."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/raw/football-data"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/football1.sqlite"),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    files = discover_season_files(args.input_dir)
    result = build_database(files, args.output)
    print(f"built {args.output}: {result['matches']} matches from {result['files']} files")


if __name__ == "__main__":
    main()
