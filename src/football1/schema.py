from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AvailabilityClass(str, Enum):
    FIXTURE = "fixture"
    OUTCOME = "outcome"
    POST_MATCH = "post_match"
    MARKET = "market"
    UNKNOWN = "unknown"


OUTCOME_COLUMNS = {"FTHG", "HG", "FTAG", "AG", "FTR", "Res", "HTHG", "HTAG", "HTR"}

POST_MATCH_COLUMNS = {
    "Attendance", "Referee", "HS", "AS", "HST", "AST", "HHW", "AHW",
    "HC", "AC", "HF", "AF", "HFKC", "AFKC", "HO", "AO", "HY", "AY",
    "HR", "AR", "HBP", "ABP", "HxG", "AxG",
}

FIXTURE_COLUMNS = {"Div", "Date", "Time", "HomeTeam", "AwayTeam"}

# Prefixes documented in Football-Data's notes.txt plus currently observed fields.
# Historical bookmaker names are retained because old seasons remain part of the
# research universe. Closing total-goals / Asian-handicap columns add C to the
# relevant market abbreviation (for example PC>2.5, PCAHH, AHCh).
MARKET_PREFIXES = (
    "1XB", "B365", "BF", "BFD", "BMGM", "BV", "BS", "BW", "CL", "GB", "IW",
    "LB", "PP", "PS", "PH", "PD", "PA", "SK", "SO", "SB", "SJ", "SY", "VC",
    "WH", "Bb", "Max", "Avg", "BFE", "P>", "P<", "PC", "AHh", "AHC",
)


def classify_column(name: str) -> AvailabilityClass:
    if name in FIXTURE_COLUMNS:
        return AvailabilityClass.FIXTURE
    if name in OUTCOME_COLUMNS:
        return AvailabilityClass.OUTCOME
    if name in POST_MATCH_COLUMNS:
        return AvailabilityClass.POST_MATCH
    if name.startswith(MARKET_PREFIXES):
        return AvailabilityClass.MARKET
    return AvailabilityClass.UNKNOWN


@dataclass(frozen=True)
class ColumnInventory:
    name: str
    availability: AvailabilityClass
