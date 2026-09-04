from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


NEUTRAL_PPG = 1.35
NEUTRAL_GOALS = 1.35
NEUTRAL_SHOTS = 12.0
NEUTRAL_SOT = 4.0
PRIOR_WEIGHT = 2.0
ELO_INITIAL = 1500.0
ELO_HOME_ADVANTAGE = 60.0
ELO_K = 20.0


@dataclass(frozen=True)
class TeamGame:
    match_date: str
    points: float
    goals_for: float
    goals_against: float
    shots_for: float | None
    shots_against: float | None
    sot_for: float | None
    sot_against: float | None


@dataclass(frozen=True)
class FeatureRow:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    elo_diff: float
    ppg5_diff: float
    gf5_diff: float
    ga5_diff: float
    shots5_diff: float
    shots_allowed5_diff: float
    sot5_diff: float
    sot_allowed5_diff: float
    ppg10_diff: float
    gf10_diff: float
    ga10_diff: float
    rest_days_diff: float
    log_prior_games_home: float
    log_prior_games_away: float
    b365_home: float | None
    b365_draw: float | None
    b365_away: float | None


FEATURE_NAMES = (
    "elo_diff",
    "ppg5_diff",
    "gf5_diff",
    "ga5_diff",
    "shots5_diff",
    "shots_allowed5_diff",
    "sot5_diff",
    "sot_allowed5_diff",
    "ppg10_diff",
    "gf10_diff",
    "ga10_diff",
    "rest_days_diff",
    "log_prior_games_home",
    "log_prior_games_away",
)


class TeamState:
    def __init__(self) -> None:
        self.games: deque[TeamGame] = deque(maxlen=10)
        self.total_games = 0
        self.last_date: str | None = None
        self.elo = ELO_INITIAL

    def recent(self, n: int) -> list[TeamGame]:
        return list(self.games)[-n:]


def _smoothed_mean(values: Iterable[float | None], neutral: float) -> float:
    observed = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    return (sum(observed) + PRIOR_WEIGHT * neutral) / (len(observed) + PRIOR_WEIGHT)


def _summarize(state: TeamState, n: int) -> dict[str, float]:
    games = state.recent(n)
    return {
        "ppg": _smoothed_mean((g.points for g in games), NEUTRAL_PPG),
        "gf": _smoothed_mean((g.goals_for for g in games), NEUTRAL_GOALS),
        "ga": _smoothed_mean((g.goals_against for g in games), NEUTRAL_GOALS),
        "shots_for": _smoothed_mean((g.shots_for for g in games), NEUTRAL_SHOTS),
        "shots_against": _smoothed_mean((g.shots_against for g in games), NEUTRAL_SHOTS),
        "sot_for": _smoothed_mean((g.sot_for for g in games), NEUTRAL_SOT),
        "sot_against": _smoothed_mean((g.sot_against for g in games), NEUTRAL_SOT),
    }


def _rest_days(state: TeamState, current_date: str) -> float:
    if state.last_date is None:
        return 7.0
    days = (date.fromisoformat(current_date) - date.fromisoformat(state.last_date)).days
    # Very long gaps are not assumed to provide linearly increasing recovery value.
    return float(max(0, min(days, 30)))


def _optional_float(raw: dict[str, object], key: str) -> float | None:
    value = raw.get(key)
    if value is None or str(value).strip() == "":
        return None
    try:
        x = float(str(value).strip())
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _b365(raw: dict[str, object]) -> tuple[float | None, float | None, float | None]:
    vals = tuple(_optional_float(raw, key) for key in ("B365H", "B365D", "B365A"))
    if all(v is not None and v > 1.0 for v in vals):
        return vals  # type: ignore[return-value]
    return (None, None, None)


def _expected_home(elo_home: float, elo_away: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-(elo_home + ELO_HOME_ADVANTAGE - elo_away) / 400.0))


def _actual_home(result: str) -> float:
    return {"H": 1.0, "D": 0.5, "A": 0.0}[result]


def _points(result: str, home: bool) -> float:
    if result == "D":
        return 1.0
    if (result == "H" and home) or (result == "A" and not home):
        return 3.0
    return 0.0


def _make_feature_row(record: sqlite3.Row, home: TeamState, away: TeamState) -> FeatureRow:
    raw: dict[str, object] = json.loads(record["raw_json"])
    h5, a5 = _summarize(home, 5), _summarize(away, 5)
    h10, a10 = _summarize(home, 10), _summarize(away, 10)
    b365h, b365d, b365a = _b365(raw)
    return FeatureRow(
        match_id=record["match_id"],
        season_start_year=int(record["season_start_year"]),
        match_date=record["match_date"],
        home_team=record["home_team"],
        away_team=record["away_team"],
        result=record["ftr"],
        elo_diff=home.elo - away.elo,
        ppg5_diff=h5["ppg"] - a5["ppg"],
        gf5_diff=h5["gf"] - a5["gf"],
        ga5_diff=h5["ga"] - a5["ga"],
        shots5_diff=h5["shots_for"] - a5["shots_for"],
        shots_allowed5_diff=h5["shots_against"] - a5["shots_against"],
        sot5_diff=h5["sot_for"] - a5["sot_for"],
        sot_allowed5_diff=h5["sot_against"] - a5["sot_against"],
        ppg10_diff=h10["ppg"] - a10["ppg"],
        gf10_diff=h10["gf"] - a10["gf"],
        ga10_diff=h10["ga"] - a10["ga"],
        rest_days_diff=_rest_days(home, record["match_date"]) - _rest_days(away, record["match_date"]),
        log_prior_games_home=math.log1p(home.total_games),
        log_prior_games_away=math.log1p(away.total_games),
        b365_home=b365h,
        b365_draw=b365d,
        b365_away=b365a,
    )


def _update_state(record: sqlite3.Row, states: dict[str, TeamState]) -> None:
    raw: dict[str, object] = json.loads(record["raw_json"])
    home = states[record["home_team"]]
    away = states[record["away_team"]]
    result = record["ftr"]

    home.games.append(
        TeamGame(
            match_date=record["match_date"],
            points=_points(result, True),
            goals_for=float(record["fthg"]),
            goals_against=float(record["ftag"]),
            shots_for=_optional_float(raw, "HS"),
            shots_against=_optional_float(raw, "AS"),
            sot_for=_optional_float(raw, "HST"),
            sot_against=_optional_float(raw, "AST"),
        )
    )
    away.games.append(
        TeamGame(
            match_date=record["match_date"],
            points=_points(result, False),
            goals_for=float(record["ftag"]),
            goals_against=float(record["fthg"]),
            shots_for=_optional_float(raw, "AS"),
            shots_against=_optional_float(raw, "HS"),
            sot_for=_optional_float(raw, "AST"),
            sot_against=_optional_float(raw, "HST"),
        )
    )
    home.total_games += 1
    away.total_games += 1
    home.last_date = record["match_date"]
    away.last_date = record["match_date"]

    expected = _expected_home(home.elo, away.elo)
    delta = ELO_K * (_actual_home(result) - expected)
    home.elo += delta
    away.elo -= delta


def build_feature_rows(db_path: Path) -> list[FeatureRow]:
    """Build strictly pre-match features.

    All fixtures on a calendar date are snapshotted before any result from that
    date updates team state. This is deliberately conservative for historical
    seasons whose files do not contain reliable kickoff timestamps.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        records = conn.execute(
            """
            SELECT match_id, season_start_year, match_date, kickoff_time,
                   home_team, away_team, fthg, ftag, ftr, raw_json
            FROM matches
            ORDER BY match_date, match_id
            """
        ).fetchall()
    finally:
        conn.close()

    states: dict[str, TeamState] = defaultdict(TeamState)
    rows: list[FeatureRow] = []
    i = 0
    while i < len(records):
        match_date = records[i]["match_date"]
        j = i
        while j < len(records) and records[j]["match_date"] == match_date:
            j += 1
        day_records = records[i:j]

        # Snapshot all predictions/features first: no same-day result can leak.
        for record in day_records:
            rows.append(
                _make_feature_row(
                    record,
                    states[record["home_team"]],
                    states[record["away_team"]],
                )
            )

        # Only after every fixture on this date has been snapshotted do results
        # become available to future dates.
        for record in day_records:
            _update_state(record, states)
        i = j

    return rows


def feature_vector(row: FeatureRow) -> list[float]:
    return [float(getattr(row, name)) for name in FEATURE_NAMES]


def rows_as_dicts(rows: Iterable[FeatureRow]) -> list[dict[str, object]]:
    return [asdict(row) for row in rows]
