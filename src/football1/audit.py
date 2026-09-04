from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from football1.build_db import discover_season_files
from football1.schema import AvailabilityClass, classify_column


PINNACLE_SOURCES = {"PS", "P"}

# Explicit 1X2 source stems prevent ambiguous parsing. In particular, VC is a
# historical bookmaker abbreviation, so VCH/VCD/VCA are pre-closing VC odds,
# not closing odds for an imaginary source "V". Closing fields add C after the
# source stem (for example B365CH/B365CD/B365CA and VCCH/VCCD/VCCA).
ONE_X_TWO_SOURCES = (
    "1XB", "B365", "BF", "BFD", "BFE", "BMGM", "BS", "BV", "BW",
    "CL", "GB", "IW", "LB", "P", "PP", "PS", "SB", "SJ", "SK",
    "SKB", "SO", "SY", "VC", "WH", "BbAv", "BbMx", "Avg", "Max",
)


@dataclass(frozen=True)
class OddsTripletAudit:
    source: str
    phase: str
    columns: tuple[str, str, str]
    rows_with_all_three: int
    row_count: int
    coverage: float
    warning: str | None = None


@dataclass(frozen=True)
class SeasonAudit:
    season_start_year: int
    source_file: str
    row_count: int
    completed_rows: int
    column_count: int
    columns: list[str]
    unknown_columns: list[str]
    odds_triplets: list[OddsTripletAudit]


def _is_valid_decimal_odd(value: str | None) -> bool:
    if value is None or value.strip() == "":
        return False
    try:
        return float(value) > 1.0
    except ValueError:
        return False


def find_1x2_triplets(columns: list[str]) -> list[tuple[str, str, tuple[str, str, str]]]:
    names = set(columns)
    triplets: list[tuple[str, str, tuple[str, str, str]]] = []

    for source in ONE_X_TWO_SOURCES:
        pre = (f"{source}H", f"{source}D", f"{source}A")
        if all(c in names for c in pre) and all(
            classify_column(c) is AvailabilityClass.MARKET for c in pre
        ):
            triplets.append((source, "pre_closing", pre))

        closing = (f"{source}CH", f"{source}CD", f"{source}CA")
        if all(c in names for c in closing) and all(
            classify_column(c) is AvailabilityClass.MARKET for c in closing
        ):
            triplets.append((source, "closing", closing))

    return triplets


def audit_season_file(path: Path, season_start_year: int) -> SeasonAudit:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no CSV header")
        columns = list(reader.fieldnames)
        rows = [row for row in reader if any((v or "").strip() for v in row.values())]

    completed_rows = sum(
        1 for row in rows if (row.get("FTR") or row.get("Res") or "").strip() in {"H", "D", "A"}
    )
    unknown_columns = sorted(
        c for c in columns if classify_column(c) is AvailabilityClass.UNKNOWN
    )

    odds_audits: list[OddsTripletAudit] = []
    for source, phase, trio in find_1x2_triplets(columns):
        valid = sum(
            1 for row in rows if all(_is_valid_decimal_odd(row.get(c)) for c in trio)
        )
        warning = None
        if source in PINNACLE_SOURCES and season_start_year >= 2025:
            warning = "Football-Data warns Pinnacle odds may be stale from 2025-07-23 onward"
        odds_audits.append(
            OddsTripletAudit(
                source=source,
                phase=phase,
                columns=trio,
                rows_with_all_three=valid,
                row_count=len(rows),
                coverage=(valid / len(rows)) if rows else 0.0,
                warning=warning,
            )
        )

    return SeasonAudit(
        season_start_year=season_start_year,
        source_file=path.name,
        row_count=len(rows),
        completed_rows=completed_rows,
        column_count=len(columns),
        columns=columns,
        unknown_columns=unknown_columns,
        odds_triplets=odds_audits,
    )


def audit_directory(input_dir: Path) -> dict[str, object]:
    seasons = [audit_season_file(path, year) for year, path in discover_season_files(input_dir)]
    union = sorted({column for season in seasons for column in season.columns})
    intersection = sorted(set(seasons[0].columns).intersection(*(set(s.columns) for s in seasons[1:]))) if seasons else []
    return {
        "season_count": len(seasons),
        "total_rows": sum(s.row_count for s in seasons),
        "total_completed_rows": sum(s.completed_rows for s in seasons),
        "schema_union": union,
        "schema_intersection": intersection,
        "seasons": [asdict(s) for s in seasons],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit downloaded Football-Data EPL CSVs before modelling.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw/football-data"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = audit_directory(args.input_dir)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote audit report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
