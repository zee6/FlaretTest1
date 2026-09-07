from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from football1.features import build_feature_rows
from football1.home_away import (
    NEUTRAL_GOALS,
    NEUTRAL_PPG,
    PRIOR_WEIGHT,
    HomeAwayRow,
    _parse_market_probs,
    _points,
    build_home_away_rows,
)
from football1.home_away_ablation import (
    ALPHA,
    BASELINE,
    PLUS_VENUE,
    _delta,
    _metrics,
    fit_variant,
    predict_variant,
)
from football1.offset_slant import _market_probs
from football1.recency_audit import recency_weight


VENUE_HALF_LIFE_DAYS = (15.0, 30.0, 60.0, 120.0)


@dataclass(frozen=True)
class DatedVenueGame:
    match_date: str
    points: float
    goals_for: float
    goals_against: float


def venue_recency_summary(
    games: deque[DatedVenueGame] | list[DatedVenueGame],
    n: int,
    *,
    current_date: str,
    half_life_days: float,
) -> tuple[float, float]:
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    current = date.fromisoformat(current_date)
    recent = list(games)[-n:]
    weighted_points = 0.0
    weighted_gf = 0.0
    weighted_ga = 0.0
    total_weight = 0.0
    for game in recent:
        age_days = (current - date.fromisoformat(game.match_date)).days
        if age_days < 0:
            raise ValueError("venue history contains a future match")
        weight = recency_weight(age_days, half_life_days)
        weighted_points += weight * game.points
        weighted_gf += weight * game.goals_for
        weighted_ga += weight * game.goals_against
        total_weight += weight

    denominator = total_weight + PRIOR_WEIGHT
    ppg = (weighted_points + PRIOR_WEIGHT * NEUTRAL_PPG) / denominator
    gf = (weighted_gf + PRIOR_WEIGHT * NEUTRAL_GOALS) / denominator
    ga = (weighted_ga + PRIOR_WEIGHT * NEUTRAL_GOALS) / denominator
    return ppg, gf - ga


def build_home_away_recency_rows(db_path: Path, *, half_life_days: float) -> list[HomeAwayRow]:
    """Build leakage-safe home-only/away-only form with exponential time decay."""
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")

    conn = sqlite3.connect(db_path)
    try:
        records = conn.execute(
            """
            SELECT match_id, season_start_year, match_date, home_team, away_team,
                   fthg, ftag, ftr, raw_json
            FROM matches
            ORDER BY match_date, match_id
            """
        ).fetchall()
    finally:
        conn.close()

    home_games: dict[str, deque[DatedVenueGame]] = defaultdict(lambda: deque(maxlen=10))
    away_games: dict[str, deque[DatedVenueGame]] = defaultdict(lambda: deque(maxlen=10))
    rows: list[HomeAwayRow] = []

    i = 0
    while i < len(records):
        current_date = str(records[i][2])
        j = i
        while j < len(records) and str(records[j][2]) == current_date:
            j += 1
        day = records[i:j]

        # Snapshot every fixture on a calendar date before any same-date result is added.
        for record in day:
            match_id, season, match_date, home, away, _, _, result, raw_json = record
            home_ppg5, home_gd5 = venue_recency_summary(
                home_games[str(home)], 5, current_date=str(match_date), half_life_days=half_life_days
            )
            away_ppg5, away_gd5 = venue_recency_summary(
                away_games[str(away)], 5, current_date=str(match_date), half_life_days=half_life_days
            )
            home_ppg10, home_gd10 = venue_recency_summary(
                home_games[str(home)], 10, current_date=str(match_date), half_life_days=half_life_days
            )
            away_ppg10, away_gd10 = venue_recency_summary(
                away_games[str(away)], 10, current_date=str(match_date), half_life_days=half_life_days
            )
            rows.append(
                HomeAwayRow(
                    match_id=str(match_id),
                    season_start_year=int(season),
                    match_date=str(match_date),
                    home_team=str(home),
                    away_team=str(away),
                    result=str(result),
                    venue_ppg5_diff=home_ppg5 - away_ppg5,
                    venue_gd5_diff=home_gd5 - away_gd5,
                    venue_ppg10_diff=home_ppg10 - away_ppg10,
                    venue_gd10_diff=home_gd10 - away_gd10,
                    market_probs=_parse_market_probs(str(raw_json)),
                )
            )

        for record in day:
            _, _, match_date, home, away, fthg, ftag, result, _ = record
            home_games[str(home)].append(
                DatedVenueGame(
                    match_date=str(match_date),
                    points=_points(str(result), home=True),
                    goals_for=float(fthg),
                    goals_against=float(ftag),
                )
            )
            away_games[str(away)].append(
                DatedVenueGame(
                    match_date=str(match_date),
                    points=_points(str(result), home=False),
                    goals_for=float(ftag),
                    goals_against=float(fthg),
                )
            )
        i = j

    return rows


def _row_map(rows: list[HomeAwayRow]) -> dict[str, HomeAwayRow]:
    return {row.match_id: row for row in rows}


def walk_forward_home_away_recency_audit(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = ALPHA,
    half_lives: tuple[float, ...] = VENUE_HALF_LIFE_DAYS,
) -> dict[str, object]:
    if any(value <= 0 for value in half_lives):
        raise ValueError("all half-lives must be positive")

    rows = build_feature_rows(db_path)
    equal_weight_map = _row_map(build_home_away_rows(db_path))
    venue_maps: dict[str, dict[str, HomeAwayRow]] = {
        "equal_weight_home_away_control": equal_weight_map,
    }
    for half_life in half_lives:
        venue_maps[f"home_away_recency_{int(half_life)}d"] = _row_map(
            build_home_away_recency_rows(db_path, half_life_days=half_life)
        )

    expected_ids = {row.match_id for row in rows}
    for name, venue_map in venue_maps.items():
        if set(venue_map) != expected_ids:
            missing = len(expected_ids - set(venue_map))
            extra = len(set(venue_map) - expected_ids)
            raise RuntimeError(f"venue variant {name} does not align with baseline matches: missing={missing} extra={extra}")

    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_raw: list[tuple[tuple[float, float, float], str]] = []
    all_baseline: list[tuple[tuple[float, float, float], str]] = []
    all_venue: dict[str, list[tuple[tuple[float, float, float], str]]] = {name: [] for name in venue_maps}
    season_reports: list[dict[str, object]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train = [row for row in rows if row.season_start_year in seasons[:test_index]]
        test = [row for row in rows if row.season_start_year == test_season]

        raw_items = [(_market_probs(row), row.result) for row in test]
        raw_metrics = _metrics(raw_items)
        all_raw.extend(raw_items)

        baseline_model = fit_variant(
            train,
            variant=BASELINE,
            venue_by_match=equal_weight_map,
            alpha=alpha,
        )
        baseline_items = [(predict_variant(baseline_model, row, equal_weight_map), row.result) for row in test]
        baseline_metrics = _metrics(baseline_items)
        all_baseline.extend(baseline_items)

        venue_reports: dict[str, object] = {}
        for name, venue_map in venue_maps.items():
            model = fit_variant(
                train,
                variant=PLUS_VENUE,
                venue_by_match=venue_map,
                alpha=alpha,
            )
            items = [(predict_variant(model, row, venue_map), row.result) for row in test]
            all_venue[name].extend(items)
            metrics = _metrics(items)
            venue_reports[name] = {
                **metrics,
                "log_loss_delta_vs_market": _delta(metrics["log_loss"], raw_metrics["log_loss"]),
                "brier_delta_vs_market": _delta(metrics["brier"], raw_metrics["brier"]),
                "log_loss_delta_vs_fixed_residual": _delta(metrics["log_loss"], baseline_metrics["log_loss"]),
                "brier_delta_vs_fixed_residual": _delta(metrics["brier"], baseline_metrics["brier"]),
            }

        season_reports.append(
            {
                "test_season_start_year": test_season,
                "test_matches": len(test),
                "raw_market": raw_metrics,
                "fixed_residual": baseline_metrics,
                "venue_variants": venue_reports,
            }
        )

    raw = _metrics(all_raw)
    baseline = _metrics(all_baseline)
    overall_venue: dict[str, object] = {}
    equal_metrics: dict[str, object] | None = None
    for name, items in all_venue.items():
        metrics: dict[str, object] = {
            **_metrics(items),
        }
        metrics["log_loss_delta_vs_market"] = _delta(metrics["log_loss"], raw["log_loss"])
        metrics["brier_delta_vs_market"] = _delta(metrics["brier"], raw["brier"])
        metrics["log_loss_delta_vs_fixed_residual"] = _delta(metrics["log_loss"], baseline["log_loss"])
        metrics["brier_delta_vs_fixed_residual"] = _delta(metrics["brier"], baseline["brier"])
        overall_venue[name] = metrics
        if name == "equal_weight_home_away_control":
            equal_metrics = metrics

    if equal_metrics is None:
        raise RuntimeError("equal-weight home/away control missing")

    for name, metrics_obj in overall_venue.items():
        metrics = metrics_obj
        metrics["log_loss_delta_vs_equal_weight_home_away"] = _delta(
            metrics["log_loss"], equal_metrics["log_loss"]
        )
        metrics["brier_delta_vs_equal_weight_home_away"] = _delta(
            metrics["brier"], equal_metrics["brier"]
        )
        metrics["ece_delta_vs_equal_weight_home_away"] = _delta(
            metrics["top_label_ece"], equal_metrics["top_label_ece"]
        )

    return {
        "experiment": "market_anchored_home_away_recency_historical_audit_v1",
        "status": "historical_exploratory_previously_observed_data",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "market_source": "B365 pre-closing, de-vigged immutable offset",
        "alpha": alpha,
        "half_life_days": list(half_lives),
        "fixed_residual_control": baseline,
        "overall_raw_market": raw,
        "overall_venue_variants": overall_venue,
        "change_under_test": (
            "For the home side, only its prior EPL home matches are used; for the away side, only its prior EPL away "
            "matches are used. Those venue-role histories are exponentially decayed by calendar age. The frozen market "
            "anchor, base Football 1 features, residual architecture, alpha, chronological splits and same-day leakage "
            "protection are unchanged."
        ),
        "interpretation_guard": (
            "This can detect whether venue-specific recent form contains useful predictive information. It cannot identify "
            "supporter hostility, loyalty or pressure as the cause; crowd effects, team strength, managers, injuries and "
            "other factors can produce the same statistical footprint."
        ),
        "parameter_policy": (
            "15/30/60/120-day venue half-lives are declared before this venue-recency run. The broader recency history "
            "has already been inspected, so no apparent winner here is untouched confirmation and none may be promoted "
            "from this audit."
        ),
        "seasons": season_reports,
        "warning": (
            "Treat any improvement as a zero-weight research lead. A venue-recency rule requires frozen prospective "
            "confirmation before it can affect fair prices, selections or stake size."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit exponentially decayed home-only and away-only form.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/home_away_recency_audit.json"))
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_home_away_recency_audit(
        args.database,
        min_train_seasons=args.min_train_seasons,
        alpha=args.alpha,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "decision_weight": report["decision_weight"],
        "overall_raw_market": report["overall_raw_market"],
        "fixed_residual_control": report["fixed_residual_control"],
        "overall_venue_variants": report["overall_venue_variants"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
