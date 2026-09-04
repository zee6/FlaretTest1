from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

from football1.elo import (
    BASE_RATING,
    HOME_ADVANTAGE,
    K_FACTOR,
    SEASON_CARRY,
    EloRow,
    _fit_probability_layer,
    _metrics,
    _parse_market_probs,
    _predict_probs,
    expected_home_score,
    regress_rating,
    update_ratings,
)


MIN_COHORT_SAMPLES = 3


@dataclass(frozen=True)
class PromotionMatchMeta:
    match_id: str
    season_start_year: int
    home_is_entrant: bool
    away_is_entrant: bool
    home_first_time_entry: bool
    away_first_time_entry: bool
    empirical_prior_rating: float
    prior_sample_count: int


@dataclass(frozen=True)
class CohortSample:
    season_start_year: int
    team: str
    terminal_reference_rating: float


def empirical_promoted_prior(
    samples: list[CohortSample],
    *,
    base_rating: float = BASE_RATING,
    min_samples: int = MIN_COHORT_SAMPLES,
) -> float:
    """Return the mean completed-cohort terminal rating or the neutral fallback.

    The caller is responsible for supplying only samples from seasons completed
    before the season being initialized.
    """
    if min_samples < 1:
        raise ValueError("min_samples must be at least 1")
    if len(samples) < min_samples:
        return float(base_rating)
    return float(fmean(sample.terminal_reference_rating for sample in samples))


def _load_records(db_path: Path) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            """
            SELECT match_id, season_start_year, match_date,
                   home_team, away_team, ftr, raw_json
            FROM matches
            ORDER BY season_start_year, match_date, match_id
            """
        ).fetchall()
    finally:
        conn.close()


def season_team_sets(records: list[tuple[object, ...]]) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    for record in records:
        season = int(record[1])
        result.setdefault(season, set()).update((str(record[3]), str(record[4])))
    return result


def entrants_by_season(records: list[tuple[object, ...]]) -> dict[int, set[str]]:
    teams = season_team_sets(records)
    seasons = sorted(teams)
    result: dict[int, set[str]] = {}
    for index, season in enumerate(seasons):
        if index == 0:
            result[season] = set()
        else:
            result[season] = set(teams[season] - teams[seasons[index - 1]])
    return result


def _regress_all(
    ratings: dict[str, float],
    *,
    base_rating: float,
    season_carry: float,
) -> dict[str, float]:
    return {
        team: regress_rating(
            rating,
            base_rating=base_rating,
            season_carry=season_carry,
        )
        for team, rating in ratings.items()
    }


def _make_row(
    record: tuple[object, ...],
    ratings: dict[str, float],
    *,
    base_rating: float,
    home_advantage: float,
) -> EloRow:
    match_id, season_start_year, match_date, home, away, result, raw_json = record
    home = str(home)
    away = str(away)
    home_rating = float(ratings.get(home, base_rating))
    away_rating = float(ratings.get(away, base_rating))
    return EloRow(
        match_id=str(match_id),
        season_start_year=int(season_start_year),
        match_date=str(match_date),
        home_team=home,
        away_team=away,
        result=str(result),
        home_rating=home_rating,
        away_rating=away_rating,
        elo_diff=(home_rating + home_advantage) - away_rating,
        expected_home_score=expected_home_score(
            home_rating,
            away_rating,
            home_advantage=home_advantage,
        ),
        market_probs=_parse_market_probs(str(raw_json)),
    )


def _apply_day(
    snapshots: list[tuple[str, str, str, float, float]],
    ratings: dict[str, float],
    *,
    k_factor: float,
    home_advantage: float,
) -> None:
    for home, away, result, home_rating, away_rating in snapshots:
        new_home, new_away = update_ratings(
            home_rating,
            away_rating,
            result,
            k_factor=k_factor,
            home_advantage=home_advantage,
        )
        ratings[home] = new_home
        ratings[away] = new_away


def build_promotion_prior_history(
    db_path: Path,
    *,
    base_rating: float = BASE_RATING,
    k_factor: float = K_FACTOR,
    home_advantage: float = HOME_ADVANTAGE,
    season_carry: float = SEASON_CARRY,
    min_cohort_samples: int = MIN_COHORT_SAMPLES,
) -> dict[str, object]:
    """Build neutral-entry and empirical-promotion-prior Elo histories.

    Three rating systems advance in parallel:

    * baseline: existing EPL-only Elo policy; unseen teams enter at neutral 1500.
    * adjusted: first-time EPL entrants use an empirical prior learned only from
      completed entrant cohorts; returning clubs keep their decayed last-known
      EPL rating.
    * reference: every detected entrant is reset to neutral at season start.
      Its terminal ratings form future empirical cohort samples, preventing the
      adjusted system from recursively learning from its own prior choices.

    All fixtures on the same date are snapshotted before any same-date result is
    applied in every system.
    """
    if min_cohort_samples < 1:
        raise ValueError("min_cohort_samples must be at least 1")

    records = _load_records(db_path)
    if not records:
        raise ValueError("No matches found")

    team_sets = season_team_sets(records)
    entrants_map = entrants_by_season(records)
    seasons = sorted(team_sets)

    baseline_ratings: dict[str, float] = {}
    adjusted_ratings: dict[str, float] = {}
    reference_ratings: dict[str, float] = {}
    seen_teams: set[str] = set()
    cohort_samples: list[CohortSample] = []
    baseline_rows: list[EloRow] = []
    adjusted_rows: list[EloRow] = []
    meta: dict[str, PromotionMatchMeta] = {}
    season_policy: list[dict[str, object]] = []

    current_season: int | None = None
    current_entrants: set[str] = set()
    current_first_time: set[str] = set()
    current_prior = float(base_rating)
    current_prior_sample_count = 0

    def finalize_reference_cohort(season: int, entrants: set[str]) -> None:
        for team in sorted(entrants):
            rating = reference_ratings.get(team)
            if rating is None or not math.isfinite(rating):
                continue
            cohort_samples.append(
                CohortSample(
                    season_start_year=season,
                    team=team,
                    terminal_reference_rating=float(rating),
                )
            )

    i = 0
    while i < len(records):
        season = int(records[i][1])
        match_date = str(records[i][2])

        if current_season != season:
            if current_season is not None:
                finalize_reference_cohort(current_season, current_entrants)
                baseline_ratings = _regress_all(
                    baseline_ratings,
                    base_rating=base_rating,
                    season_carry=season_carry,
                )
                adjusted_ratings = _regress_all(
                    adjusted_ratings,
                    base_rating=base_rating,
                    season_carry=season_carry,
                )
                reference_ratings = _regress_all(
                    reference_ratings,
                    base_rating=base_rating,
                    season_carry=season_carry,
                )

            current_season = season
            current_entrants = set(entrants_map[season])
            current_first_time = set(current_entrants - seen_teams)
            prior_samples = [s for s in cohort_samples if s.season_start_year < season]
            current_prior_sample_count = len(prior_samples)
            current_prior = empirical_promoted_prior(
                prior_samples,
                base_rating=base_rating,
                min_samples=min_cohort_samples,
            )

            # The reference system deliberately neutralizes every entrant so
            # terminal ratings are comparable across promoted cohorts.
            for team in current_entrants:
                reference_ratings[team] = float(base_rating)

            # Only first-time archive entrants lack usable EPL history. Clubs
            # returning after relegation retain their decayed previous rating.
            for team in current_first_time:
                adjusted_ratings[team] = float(current_prior)

            source_seasons = sorted({s.season_start_year for s in prior_samples})
            season_policy.append(
                {
                    "season_start_year": season,
                    "entrants": sorted(current_entrants),
                    "first_time_archive_entrants": sorted(current_first_time),
                    "returning_entrants": sorted(current_entrants - current_first_time),
                    "empirical_prior_rating": current_prior,
                    "prior_sample_count": current_prior_sample_count,
                    "prior_source_seasons": source_seasons,
                }
            )
            seen_teams.update(team_sets[season])

        j = i
        day_records: list[tuple[object, ...]] = []
        while (
            j < len(records)
            and int(records[j][1]) == season
            and str(records[j][2]) == match_date
        ):
            day_records.append(records[j])
            j += 1

        baseline_snapshots: list[tuple[str, str, str, float, float]] = []
        adjusted_snapshots: list[tuple[str, str, str, float, float]] = []
        reference_snapshots: list[tuple[str, str, str, float, float]] = []

        for record in day_records:
            baseline_row = _make_row(
                record,
                baseline_ratings,
                base_rating=base_rating,
                home_advantage=home_advantage,
            )
            adjusted_row = _make_row(
                record,
                adjusted_ratings,
                base_rating=base_rating,
                home_advantage=home_advantage,
            )
            reference_row = _make_row(
                record,
                reference_ratings,
                base_rating=base_rating,
                home_advantage=home_advantage,
            )
            baseline_rows.append(baseline_row)
            adjusted_rows.append(adjusted_row)
            meta[baseline_row.match_id] = PromotionMatchMeta(
                match_id=baseline_row.match_id,
                season_start_year=season,
                home_is_entrant=baseline_row.home_team in current_entrants,
                away_is_entrant=baseline_row.away_team in current_entrants,
                home_first_time_entry=baseline_row.home_team in current_first_time,
                away_first_time_entry=baseline_row.away_team in current_first_time,
                empirical_prior_rating=current_prior,
                prior_sample_count=current_prior_sample_count,
            )
            baseline_snapshots.append(
                (
                    baseline_row.home_team,
                    baseline_row.away_team,
                    baseline_row.result,
                    baseline_row.home_rating,
                    baseline_row.away_rating,
                )
            )
            adjusted_snapshots.append(
                (
                    adjusted_row.home_team,
                    adjusted_row.away_team,
                    adjusted_row.result,
                    adjusted_row.home_rating,
                    adjusted_row.away_rating,
                )
            )
            reference_snapshots.append(
                (
                    reference_row.home_team,
                    reference_row.away_team,
                    reference_row.result,
                    reference_row.home_rating,
                    reference_row.away_rating,
                )
            )

        _apply_day(
            baseline_snapshots,
            baseline_ratings,
            k_factor=k_factor,
            home_advantage=home_advantage,
        )
        _apply_day(
            adjusted_snapshots,
            adjusted_ratings,
            k_factor=k_factor,
            home_advantage=home_advantage,
        )
        _apply_day(
            reference_snapshots,
            reference_ratings,
            k_factor=k_factor,
            home_advantage=home_advantage,
        )
        i = j

    if current_season is not None:
        finalize_reference_cohort(current_season, current_entrants)

    return {
        "baseline_rows": baseline_rows,
        "adjusted_rows": adjusted_rows,
        "meta_by_match": meta,
        "season_policy": season_policy,
        "cohort_samples": cohort_samples,
        "final_baseline_ratings": baseline_ratings,
        "final_adjusted_ratings": adjusted_ratings,
    }


def _subset_metrics(
    items: list[tuple[tuple[float, float, float], str, str]],
    meta_by_match: dict[str, PromotionMatchMeta],
    *,
    first_time_only: bool,
) -> dict[str, float | int | None]:
    filtered: list[tuple[tuple[float, float, float], str]] = []
    for probs, result, match_id in items:
        meta = meta_by_match[match_id]
        if first_time_only:
            include = meta.home_first_time_entry or meta.away_first_time_entry
        else:
            include = meta.home_is_entrant or meta.away_is_entrant
        if include:
            filtered.append((probs, result))
    return _metrics(filtered)


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def walk_forward_promotion_prior(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    base_rating: float = BASE_RATING,
    k_factor: float = K_FACTOR,
    home_advantage: float = HOME_ADVANTAGE,
    season_carry: float = SEASON_CARRY,
    min_cohort_samples: int = MIN_COHORT_SAMPLES,
) -> dict[str, object]:
    history = build_promotion_prior_history(
        db_path,
        base_rating=base_rating,
        k_factor=k_factor,
        home_advantage=home_advantage,
        season_carry=season_carry,
        min_cohort_samples=min_cohort_samples,
    )
    baseline_rows = history["baseline_rows"]
    adjusted_rows = history["adjusted_rows"]
    meta_by_match = history["meta_by_match"]
    if not isinstance(baseline_rows, list) or not isinstance(adjusted_rows, list):
        raise TypeError("Unexpected promotion history row container")
    if not isinstance(meta_by_match, dict):
        raise TypeError("Unexpected promotion history metadata container")

    adjusted_by_match = {row.match_id: row for row in adjusted_rows}
    seasons = sorted({row.season_start_year for row in baseline_rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_baseline: list[tuple[tuple[float, float, float], str, str]] = []
    all_adjusted: list[tuple[tuple[float, float, float], str, str]] = []
    all_market: list[tuple[tuple[float, float, float], str, str]] = []
    reports: list[dict[str, object]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train_seasons = set(seasons[:test_index])
        train_baseline = [row for row in baseline_rows if row.season_start_year in train_seasons]
        train_adjusted = [row for row in adjusted_rows if row.season_start_year in train_seasons]
        test_baseline = [row for row in baseline_rows if row.season_start_year == test_season]

        baseline_model = _fit_probability_layer(train_baseline)
        adjusted_model = _fit_probability_layer(train_adjusted)

        baseline_items: list[tuple[tuple[float, float, float], str, str]] = []
        adjusted_items: list[tuple[tuple[float, float, float], str, str]] = []
        market_items: list[tuple[tuple[float, float, float], str, str]] = []

        for baseline_row in test_baseline:
            adjusted_row = adjusted_by_match[baseline_row.match_id]
            baseline_probs = _predict_probs(baseline_model, baseline_row)
            adjusted_probs = _predict_probs(adjusted_model, adjusted_row)
            baseline_items.append((baseline_probs, baseline_row.result, baseline_row.match_id))
            adjusted_items.append((adjusted_probs, adjusted_row.result, adjusted_row.match_id))
            if baseline_row.market_probs is not None:
                market_items.append((baseline_row.market_probs, baseline_row.result, baseline_row.match_id))

        all_baseline.extend(baseline_items)
        all_adjusted.extend(adjusted_items)
        all_market.extend(market_items)

        baseline_m = _metrics([(p, r) for p, r, _ in baseline_items])
        adjusted_m = _metrics([(p, r) for p, r, _ in adjusted_items])
        market_m = _metrics([(p, r) for p, r, _ in market_items])
        entrants_baseline = _subset_metrics(
            baseline_items,
            meta_by_match,
            first_time_only=False,
        )
        entrants_adjusted = _subset_metrics(
            adjusted_items,
            meta_by_match,
            first_time_only=False,
        )
        first_time_baseline = _subset_metrics(
            baseline_items,
            meta_by_match,
            first_time_only=True,
        )
        first_time_adjusted = _subset_metrics(
            adjusted_items,
            meta_by_match,
            first_time_only=True,
        )

        reports.append(
            {
                "test_season_start_year": test_season,
                "train_matches": len(train_baseline),
                "test_matches": len(test_baseline),
                "baseline_neutral_entry_elo": baseline_m,
                "empirical_promotion_prior_elo": adjusted_m,
                "paired_b365_pre_closing": market_m,
                "promotion_prior_minus_baseline": {
                    "log_loss": _delta(adjusted_m["log_loss"], baseline_m["log_loss"]),
                    "brier": _delta(adjusted_m["brier"], baseline_m["brier"]),
                },
                "entrant_involved_matches": {
                    "baseline": entrants_baseline,
                    "promotion_prior": entrants_adjusted,
                    "log_loss_delta": _delta(
                        entrants_adjusted["log_loss"], entrants_baseline["log_loss"]
                    ),
                    "brier_delta": _delta(
                        entrants_adjusted["brier"], entrants_baseline["brier"]
                    ),
                },
                "first_time_archive_entrant_matches": {
                    "baseline": first_time_baseline,
                    "promotion_prior": first_time_adjusted,
                    "log_loss_delta": _delta(
                        first_time_adjusted["log_loss"], first_time_baseline["log_loss"]
                    ),
                    "brier_delta": _delta(
                        first_time_adjusted["brier"], first_time_baseline["brier"]
                    ),
                },
            }
        )

    overall_baseline = _metrics([(p, r) for p, r, _ in all_baseline])
    overall_adjusted = _metrics([(p, r) for p, r, _ in all_adjusted])
    overall_market = _metrics([(p, r) for p, r, _ in all_market])
    entrants_baseline = _subset_metrics(all_baseline, meta_by_match, first_time_only=False)
    entrants_adjusted = _subset_metrics(all_adjusted, meta_by_match, first_time_only=False)
    first_time_baseline = _subset_metrics(all_baseline, meta_by_match, first_time_only=True)
    first_time_adjusted = _subset_metrics(all_adjusted, meta_by_match, first_time_only=True)

    cohort_samples = history["cohort_samples"]
    season_policy = history["season_policy"]
    final_adjusted = history["final_adjusted_ratings"]
    if not isinstance(cohort_samples, list) or not isinstance(season_policy, list):
        raise TypeError("Unexpected promotion history diagnostics")
    if not isinstance(final_adjusted, dict):
        raise TypeError("Unexpected final rating container")

    return {
        "experiment": "empirical_promoted_team_elo_prior_v1",
        "status": "historical_structural_audit_zero_decision_weight",
        "decision_weight": 0.0,
        "data_scope": "EPL only; no Championship or other lower-league inputs in v1",
        "entry_definition": "team present in current EPL season but absent from immediately previous EPL season",
        "first_time_definition": "detected entrant with no earlier EPL appearance in the available archive",
        "returning_team_policy": "retain decayed last-known EPL Elo; do not overwrite known EPL evidence with the cohort prior",
        "new_team_policy": "first-time archive entrants receive the arithmetic mean terminal neutral-reference Elo of completed earlier entrant cohorts once at least three samples exist; otherwise neutral 1500",
        "cohort_reference_policy": "parallel Elo resets every detected entrant to neutral at season start; terminal season rating becomes a sample only for future seasons",
        "same_day_policy": "all systems freeze every fixture on a date before any same-date result update",
        "season_regression": season_carry,
        "elo_parameters": {
            "base_rating": base_rating,
            "k_factor": k_factor,
            "home_advantage": home_advantage,
            "min_cohort_samples": min_cohort_samples,
        },
        "hyperparameter_policy": "all v1 rules fixed before held-out scoring; no held-out season tuning",
        "overall": {
            "baseline_neutral_entry_elo": overall_baseline,
            "empirical_promotion_prior_elo": overall_adjusted,
            "paired_b365_pre_closing": overall_market,
            "promotion_prior_minus_baseline": {
                "log_loss": _delta(overall_adjusted["log_loss"], overall_baseline["log_loss"]),
                "brier": _delta(overall_adjusted["brier"], overall_baseline["brier"]),
            },
            "promotion_prior_minus_market": {
                "log_loss": _delta(overall_adjusted["log_loss"], overall_market["log_loss"]),
                "brier": _delta(overall_adjusted["brier"], overall_market["brier"]),
            },
            "entrant_involved_matches": {
                "baseline": entrants_baseline,
                "promotion_prior": entrants_adjusted,
                "log_loss_delta": _delta(
                    entrants_adjusted["log_loss"], entrants_baseline["log_loss"]
                ),
                "brier_delta": _delta(
                    entrants_adjusted["brier"], entrants_baseline["brier"]
                ),
            },
            "first_time_archive_entrant_matches": {
                "baseline": first_time_baseline,
                "promotion_prior": first_time_adjusted,
                "log_loss_delta": _delta(
                    first_time_adjusted["log_loss"], first_time_baseline["log_loss"]
                ),
                "brier_delta": _delta(
                    first_time_adjusted["brier"], first_time_baseline["brier"]
                ),
            },
        },
        "season_policy": season_policy,
        "cohort_samples": [
            {
                "season_start_year": sample.season_start_year,
                "team": sample.team,
                "terminal_reference_rating": sample.terminal_reference_rating,
            }
            for sample in cohort_samples
        ],
        "final_adjusted_ratings": [
            {"team": team, "rating": float(rating)}
            for team, rating in sorted(final_adjusted.items(), key=lambda item: (-item[1], item[0]))
        ],
        "seasons": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Leakage-safe EPL promoted-team empirical Elo prior audit."
    )
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--min-cohort-samples", type=int, default=MIN_COHORT_SAMPLES)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_promotion_prior(
        args.database,
        min_train_seasons=args.min_train_seasons,
        min_cohort_samples=args.min_cohort_samples,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote promotion-prior report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
