from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AvailabilityClass(str, Enum):
    FIXTURE = "fixture"
    OUTCOME = "outcome"
    POST_MATCH = "post_match"
    MARKET = "market"
    UNKNOWN = "unknown"


OUTCOME_COLUMNS = {
    "FTHG",
    "FTAG",
    "FTR",
    "HTHG",
    "HTAG",
    "HTR",
}

POST_MATCH_COLUMNS = {
    "HS",
    "AS",
    "HST",
    "AST",
    "HF",
    "AF",
    "HC",
    "AC",
    "HY",
    "AY",
    "HR",
    "AR",
}

FIXTURE_COLUMNS = {
    "Div",
    "Date",
    "Time",
    "HomeTeam",
    "AwayTeam",
}

MARKET_PREFIXES = (
    "B365",
    "BW",
    "IW",
    "PS",
    "WH",
    "VC",
    "Max",
    "Avg",
    "Bb",
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
