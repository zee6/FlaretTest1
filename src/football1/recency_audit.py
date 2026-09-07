from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from football1.features import (
    ELO_HOME_ADVANTAGE,
    ELO_INITIAL,
    ELO_K,
    NEUTRAL_GOALS,
    NEUTRAL_PPG,
    NEUTRAL_SHOTS,
    NEUTRAL_SOT,
    PRIOR_WEIGHT,
    FeatureRow,
    TeamGame,
    build_feature_rows,
)
from football1.model_baseline import _mean_metrics, _top_label_ece
from football1.offset_slant import _market_probs, fit_offset_slant


HALF_LIFE_DAYS = (30.0, 60.0, 120.0)
ALPHA = 0.10


class TeamState:
    def __init__(self) -> None:
        self.games: deque[TeamGame] = deque(maxlen=10)
        self.total_games = 0
        self.last_date: str | None = None
        self.elo = ELO_INITIAL

    def recent(self, n: int) -> list[TeamGame]:
        return list(self.games)[-n:]


def recency_weight(age_days: int, half_life_days: float) -> float:
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    if age_days < 0:
        raise ValueError("age_days must be non-negative")
    return math.exp(-math.log(2.0) * float(age_days) / half_life_days)


def weighted_smoothed_mean(
    games: Iterable[TeamGame],
    *,
    current_date: str,
    attribute: str,
    neutral: float,
    half_life_days: float,
) -> float:
    current = date.fromisoformat(current_date)
    weighted_total = 0.0
    total_weight = 0.0
    for game in games:
        raw = getattr(game, attribute)
        if raw is None:
            continue
        value = float(raw)
        if not math.isfinite(value):
            continue
        age = (current - date.fromisoformat(game.match_date)).days
        weight = recency_weight(max(age, 0), half_life_days)
        weighted_total += weight * value
        total_weight += weight
    return (weighted_total + PRIOR_WEIGHT * neutral) / (total_weight + PRIOR_WEIGHT)


def _summarize(state: TeamState, n: int, *, current_date: str, half_life_days: float) -> dict[str, float]:
    games = state.recent(n)
    return {
        "ppg": weighted_smoothed_mean(
            games, current_date=current_date, attribute="points", neutral=NEUTRAL_PPG, half_life_days=half_life_days
        ),
        "gf": weighted_smoothed_mean(
            games, current_date=current_date, attribute="goals_for", neutral=NEUTRAL_GOALS, half_life_days=half_life_days
        ),
        "ga": weighted_smoothed_mean(
            games, current_date=current_date, attribute="goals_against", neutral=NEUTRAL_GOALS, half_life_days=half_life_days
        ),
        "shots_for": weighted_smoothed_mean(
            games, current_date=current_date, attribute="shots_for", neutral=NEUTRAL_SHOTS, half_life_days=half_life_days
        ),
        "shots_against": weighted_smoothed_mean(
            games, current_date=current_date, attribute="shots_against", neutral=NEUTRAL_SHOTS, half_life_days=half_life_days
        ),
        "sot_for": weighted_smoothed_mean(
            games, current_date=current_date, attribute="sot_for", neutral=NEUTRAL_SOT, half_life_days=half_life_days
        ),
        "sot_against": weighted_smoothed_mean(
            games, current_date=current_date, attribute="sot_against", neutral=NEUTRAL_SOT, half_life_days=half_life_days
        ),
    }


def _optional_float(raw: dict[str, object], key: str) -> float | None:
    value = raw.get(key)
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _b365(raw: dict[str, object]) -> tuple[float | None, float | None, float | None]:
    values = tuple(_optional_float(raw, key) for key in ("B365H", "B365D", "B365A"))
    if all(value is not None and value > 1.0 for value in values):
        return values  # type: ignore[return-value]
    return (None, None, None)


def _rest_days(state: TeamState, current_date: str) -> float:
    if state.last_date is None:
        return 7.0
    days = (date.fromisoformat(current_date) - date.fromisoformat(state.last_date)).days
    return float(max(0, min(days, 30)))


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


def _make_row(record: sqlite3.Row, home: TeamState, away: TeamState, *, half_life_days: float) -> FeatureRow:
    raw: dict[str, object] = json.loads(record["raw_json"])
    current_date = str(record["match_date"])
    h5 = _summarize(home, 5, current_date=current_date, half_life_days=half_life_days)
    a5 = _summarize(away, 5, current_date=current_date, half_life_days=half_life_days)
    h10 = _summarize(home, 10, current_date=current_date, half_life_days=half_life_days)
    a10 = _summarize(away, 10, current_date=current_date, half_life_days=half_life_days)
    b365h, b365d, b365a = _b365(raw)
    return FeatureRow(
        match_id=str(record["match_id"]),
        season_start_year=int(record["season_start_year"]),
        match_date=current_date,
        home_team=str(record["home_team"]),
        away_team=str(record["away_team"]),
        result=str(record["ftr"]),
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
        rest_days_diff=_rest_days(home, current_date) - _rest_days(away, current_date),
        log_prior_games_home=math.log1p(home.total_games),
        log_prior_games_away=math.log1p(away.total_games),
        b365_home=b365h,
        b365_draw=b365d,
        b365_away=b365a,
    )


def _update_state(record: sqlite3.Row, states: dict[str, TeamState]) -> None:
    raw: dict[str, object] = json.loads(record["raw_json"])
    home = states[str(record["home_team"])]
    away = states[str(record["away_team"])]
    result = str(record["ftr"])
    match_date = str(record["match_date"])
    home.games.append(
        TeamGame(
            match_date=match_date,
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
            match_date=match_date,
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
    home.last_date = match_date
    away.last_date = match_date
    expected = _expected_home(home.elo, away.elo)
    change = ELO_K * (_actual_home(result) - expected)
    home.elo += change
    away.elo -= change


def build_recency_feature_rows(db_path: Path, *, half_life_days: float) -> list[FeatureRow]:
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
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
        match_date = str(records[i]["match_date"])
        j = i
        while j < len(records) and str(records[j]["match_date"]) == match_date:
            j += 1
        day_records = records[i:j]
        for record in day_records:
            rows.append(
                _make_row(
                    record,
                    states[str(record["home_team"])],
                    states[str(record["away_team"])],
                    half_life_days=half_life_days,
                )
            )
        for record in day_records:
            _update_state(record, states)
        i = j
    return rows


def _metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    metrics = _mean_metrics(items)
    metrics["top_label_ece"] = _top_label_ece(items)
    return metrics


def _delta(left: object, right: object) -> float | None:
    if left is None or right is None:
        return None
    return float(left) - float(right)


def walk_forward_recency_audit(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = ALPHA,
    half_lives: tuple[float, ...] = HALF_LIFE_DAYS,
) -> dict[str, object]:
    if any(value <= 0 for value in half_lives):
        raise ValueError("all half-lives must be positive")

    baseline_rows = build_feature_rows(db_path)
    variants: dict[str, list[FeatureRow]] = {"equal_weight_control": baseline_rows}
    for half_life in half_lives:
        variants[f"recency_{int(half_life)}d"] = build_recency_feature_rows(db_path, half_life_days=half_life)

    baseline_ids = [row.match_id for row in baseline_rows]
    for name, rows in variants.items():
        if [row.match_id for row in rows] != baseline_ids:
            raise RuntimeError(f"recency variant {name} does not align exactly with baseline matches")

    seasons = sorted({row.season_start_year for row in baseline_rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_raw: list[tuple[tuple[float, float, float], str]] = []
    all_variant_items: dict[str, list[tuple[tuple[float, float, float], str]]] = {name: [] for name in variants}
    season_reports: list[dict[str, object]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        baseline_test = [row for row in baseline_rows if row.season_start_year == test_season]
        raw_items = [(_market_probs(row), row.result) for row in baseline_test]
        raw_metrics = _metrics(raw_items)
        all_raw.extend(raw_items)
        season_variants: dict[str, object] = {}

        for name, rows in variants.items():
            train = [row for row in rows if row.season_start_year in seasons[:test_index]]
            test = [row for row in rows if row.season_start_year == test_season]
            model = fit_offset_slant(train, alpha=alpha)
            items = [(model.predict(row), row.result) for row in test]
            all_variant_items[name].extend(items)
            metrics = _metrics(items)
            season_variants[name] = {
                **metrics,
                "log_loss_delta_vs_market": _delta(metrics["log_loss"], raw_metrics["log_loss"]),
                "brier_delta_vs_market": _delta(metrics["brier"], raw_metrics["brier"]),
            }
        season_reports.append(
            {
                "test_season_start_year": test_season,
                "test_matches": len(baseline_test),
                "raw_market": raw_metrics,
                "variants": season_variants,
            }
        )

    raw = _metrics(all_raw)
    overall: dict[str, object] = {}
    for name, items in all_variant_items.items():
        metrics = _metrics(items)
        overall[name] = {
            **metrics,
            "log_loss_delta_vs_market": _delta(metrics["log_loss"], raw["log_loss"]),
            "brier_delta_vs_market": _delta(metrics["brier"], raw["brier"]),
        }

    control = overall["equal_weight_control"]
    for name, metrics in overall.items():
        metrics["log_loss_delta_vs_equal_weight_control"] = _delta(metrics["log_loss"], control["log_loss"])
        metrics["brier_delta_vs_equal_weight_control"] = _delta(metrics["brier"], control["brier"])
        metrics["ece_delta_vs_equal_weight_control"] = _delta(metrics["top_label_ece"], control["top_label_ece"])

    return {
        "experiment": "recency_weighted_form_historical_audit_v1",
        "status": "historical_exploratory_previously_observed_data",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "market_source": "B365 pre-closing, de-vigged",
        "residual_model": "fixed_market_offset_football_slant_v1",
        "alpha": alpha,
        "half_life_days": list(half_lives),
        "control": "existing equal-weight last-5 / last-10 form summaries",
        "change_under_test": (
            "Only last-5 / last-10 form summaries are exponentially weighted by age. Elo, rest, priors, market anchor, "
            "feature count, residual architecture, chronological splits and same-day leakage protection remain unchanged."
        ),
        "parameter_policy": (
            "30/60/120-day half-lives are predeclared broad sensitivity probes. This inspected historical audit must not be used to select a winning half-life as validated."
        ),
        "overall_raw_market": raw,
        "overall_variants": overall,
        "seasons": season_reports,
        "warning": (
            "A recency variant that looks better on this already-inspected history is a research lead only. It requires a frozen choice and untouched prospective confirmation before product weight."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit recency-weighted Football 1 form features.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/recency_audit.json"))
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_recency_audit(args.database, min_train_seasons=args.min_train_seasons)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "decision_weight": report["decision_weight"],
        "overall_raw_market": report["overall_raw_market"],
        "overall_variants": report["overall_variants"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
