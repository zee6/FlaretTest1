from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from football1.elo import (
    BASE_RATING,
    ELO_SCALE,
    HOME_ADVANTAGE,
    K_FACTOR,
    SEASON_CARRY,
    build_elo_history,
)


def _three_year_cutoff(latest_match_date: str) -> date:
    latest = date.fromisoformat(latest_match_date)
    try:
        return latest.replace(year=latest.year - 3)
    except ValueError:
        # Feb 29 -> Feb 28 in a non-leap cutoff year.
        return latest.replace(year=latest.year - 3, day=28)


def _sample_history_for_app(
    points: list[dict[str, object]],
    *,
    latest_season: int,
    cutoff: date,
) -> list[dict[str, object]]:
    """Keep three years: current-season detail plus one exact point per older month."""
    sampled: list[dict[str, object]] = []
    older_by_month: dict[str, dict[str, object]] = {}
    for point in points:
        point_date = date.fromisoformat(str(point["date"]))
        if point_date < cutoff:
            continue
        season = int(point["season_start_year"])
        if season == latest_season:
            sampled.append(point)
        else:
            month_key = str(point["date"])[:7]
            older_by_month[month_key] = point
    sampled.extend(older_by_month.values())
    return sorted(sampled, key=lambda point: str(point["date"]))


def build_elo_research_export(db_path: Path) -> dict[str, object]:
    """Build a compact, leakage-safe Elo export for Football 1 interfaces.

    The table contains only clubs present in the latest EPL season in the
    canonical database. Every exported history point is an exact pre-match Elo
    state already frozen by ``build_elo_history``. The mobile graph covers the
    latest three years; current-season matches are kept individually and older
    months keep their final exact pre-match snapshot.
    """
    rows, final_ratings = build_elo_history(db_path)
    if not rows:
        raise ValueError("No Elo rows found")

    latest_season = max(row.season_start_year for row in rows)
    latest_rows = [row for row in rows if row.season_start_year == latest_season]
    latest_match_date = max(row.match_date for row in latest_rows)
    history_cutoff = _three_year_cutoff(latest_match_date)
    current_teams = sorted(
        {row.home_team for row in latest_rows} | {row.away_team for row in latest_rows}
    )

    full_histories: dict[str, list[dict[str, object]]] = {
        team: [] for team in current_teams
    }
    for row in rows:
        if row.home_team in full_histories:
            full_histories[row.home_team].append(
                {
                    "date": row.match_date,
                    "season_start_year": row.season_start_year,
                    "rating": float(row.home_rating),
                }
            )
        if row.away_team in full_histories:
            full_histories[row.away_team].append(
                {
                    "date": row.match_date,
                    "season_start_year": row.season_start_year,
                    "rating": float(row.away_rating),
                }
            )

    ranked_teams = sorted(
        current_teams,
        key=lambda name: (-final_ratings.get(name, BASE_RATING), name),
    )
    current_ratings: list[dict[str, object]] = []
    for rank, team in enumerate(ranked_teams, start=1):
        current = float(final_ratings.get(team, BASE_RATING))
        team_history = full_histories[team]
        five_match_reference = (
            float(team_history[-5]["rating"])
            if len(team_history) >= 5
            else float(team_history[0]["rating"])
        )
        season_points = [
            point for point in team_history if point["season_start_year"] == latest_season
        ]
        season_reference = (
            float(season_points[0]["rating"]) if season_points else current
        )
        current_ratings.append(
            {
                "rank": rank,
                "team": team,
                "rating": current,
                "change_5_matches": current - five_match_reference,
                "season_change": current - season_reference,
            }
        )

    histories = {
        team: _sample_history_for_app(
            points,
            latest_season=latest_season,
            cutoff=history_cutoff,
        )
        for team, points in full_histories.items()
    }

    return {
        "schema_version": 1,
        "model": "elo_1x2_v1",
        "latest_season_start_year": latest_season,
        "latest_match_date": latest_match_date,
        "history_start_date": history_cutoff.isoformat(),
        "parameters": {
            "base_rating": BASE_RATING,
            "scale": ELO_SCALE,
            "k_factor": K_FACTOR,
            "home_advantage": HOME_ADVANTAGE,
            "season_carry": SEASON_CARRY,
        },
        "rating_policy": "Result-only EPL Elo; H=1, D=0.5, A=0; no goal-margin multiplier.",
        "history_policy": "Every plotted value is an exact leakage-safe pre-match rating. The graph covers the latest three years. Current-season matches are kept individually; earlier months keep the final pre-match snapshot in each calendar month. Same-day results are applied only after all fixtures on that date are frozen.",
        "change_policy": "Five-match change compares the current post-result rating with the pre-match rating five EPL appearances back. Season change compares with the first pre-match rating of the latest EPL season.",
        "product_status": "CONTEXT_ONLY",
        "current_ratings": current_ratings,
        "histories": histories,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Football 1 Elo table and team histories for app research views.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("research/elo_research.json"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_elo_research_export(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote Elo research export to {args.output}: "
        f"{len(report['current_ratings'])} current teams"
    )


if __name__ == "__main__":
    main()
