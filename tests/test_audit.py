import csv
from pathlib import Path

from football1.audit import audit_season_file, find_1x2_triplets


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_finds_preclosing_and_closing_1x2_triplets():
    columns = [
        "Date", "HomeTeam", "AwayTeam", "FTR",
        "B365H", "B365D", "B365A",
        "B365CH", "B365CD", "B365CA",
    ]
    assert ("B365", "pre_closing", ("B365H", "B365D", "B365A")) in find_1x2_triplets(columns)
    assert ("B365", "closing", ("B365CH", "B365CD", "B365CA")) in find_1x2_triplets(columns)


def test_audit_counts_coverage_and_completed_rows(tmp_path: Path):
    path = tmp_path / "EPL_2627_E0.csv"
    fields = [
        "Date", "HomeTeam", "AwayTeam", "FTR",
        "B365H", "B365D", "B365A",
        "PSCH", "PSCD", "PSCA",
    ]
    _write_csv(
        path,
        fields,
        [
            {"Date": "15/08/2026", "HomeTeam": "A", "AwayTeam": "B", "FTR": "H", "B365H": "1.8", "B365D": "3.6", "B365A": "5.0", "PSCH": "1.75", "PSCD": "3.7", "PSCA": "5.2"},
            {"Date": "22/08/2026", "HomeTeam": "C", "AwayTeam": "D", "FTR": "", "B365H": "2.0", "B365D": "3.4", "B365A": "3.8", "PSCH": "", "PSCD": "", "PSCA": ""},
        ],
    )
    audit = audit_season_file(path, 2026)
    assert audit.row_count == 2
    assert audit.completed_rows == 1

    b365 = next(x for x in audit.odds_triplets if x.source == "B365" and x.phase == "pre_closing")
    assert b365.rows_with_all_three == 2
    assert b365.coverage == 1.0

    pinnacle = next(x for x in audit.odds_triplets if x.source == "PS" and x.phase == "closing")
    assert pinnacle.rows_with_all_three == 1
    assert pinnacle.coverage == 0.5
    assert pinnacle.warning is not None


def test_does_not_misclassify_post_match_home_away_fields_as_1x2():
    columns = ["HS", "AS", "HC", "AC", "HR", "AR"]
    assert find_1x2_triplets(columns) == []
