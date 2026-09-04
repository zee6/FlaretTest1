from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from football1.bayesian_strength import (
    BayesianStrengthRow,
    _fit_probability_layer as _fit_bayesian_probability_layer,
    _predict_probs as _predict_bayesian_probs,
    build_bayesian_strength_rows,
)
from football1.dixon_coles import (
    MatchRecord,
    fit_dixon_coles,
    load_matches,
    predict_match as predict_dixon_coles_match,
)
from football1.elo import (
    EloRow,
    _fit_probability_layer as _fit_elo_probability_layer,
    _predict_probs as _predict_elo_probs,
    build_elo_rows,
)
from football1.features import FeatureRow, build_feature_rows
from football1.market_baseline import score_probabilities
from football1.scoreline import ScorelineRow, build_scoreline_history


CLASS_ORDER = ("H", "D", "A")
SHADOW_NAMES = ("elo", "bayesian_strength", "poisson", "dixon_coles")
MARKET_BLEND_WEIGHT = 0.90
SHADOW_BLEND_WEIGHT = 0.10


@dataclass(frozen=True)
class DisagreementRow:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    market_probs: tuple[float, float, float]
    odds: tuple[float, float, float]
    shadow_probs: dict[str, tuple[float, float, float]]
    shadow_mean_probs: tuple[float, float, float]
    blended_probs: tuple[float, float, float]
    market_top: str
    shadow_consensus_top: str | None
    shadow_consensus_count: int
    market_alignment_count: int
    probability_dispersion: float
    mean_abs_shadow_market_distance: float


def _top_index(probs: tuple[float, float, float]) -> int:
    return max(range(3), key=lambda index: probs[index])


def _odds(row: FeatureRow) -> tuple[float, float, float] | None:
    values = (row.b365_home, row.b365_draw, row.b365_away)
    if any(value is None or value <= 1.0 for value in values):
        return None
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def _mean_probs(
    probs: list[tuple[float, float, float]],
) -> tuple[float, float, float]:
    array = np.asarray(probs, dtype=float)
    mean = array.mean(axis=0)
    mean /= mean.sum()
    return float(mean[0]), float(mean[1]), float(mean[2])


def _blend(
    market: tuple[float, float, float],
    shadow: tuple[float, float, float],
) -> tuple[float, float, float]:
    values = [
        MARKET_BLEND_WEIGHT * market[i] + SHADOW_BLEND_WEIGHT * shadow[i]
        for i in range(3)
    ]
    total = sum(values)
    return tuple(value / total for value in values)  # type: ignore[return-value]


def _metrics(
    rows: list[DisagreementRow],
    selector,
) -> dict[str, float | int | None]:
    if not rows:
        return {
            "matches": 0,
            "log_loss": None,
            "brier": None,
            "accuracy": None,
        }
    scores = [score_probabilities(selector(row), row.result) for row in rows]
    n = len(scores)
    return {
        "matches": n,
        "log_loss": sum(score.log_loss for score in scores) / n,
        "brier": sum(score.brier for score in scores) / n,
        "accuracy": sum(score.correct for score in scores) / n,
    }


def _blind_top_roi(
    rows: list[DisagreementRow],
    selector,
) -> dict[str, float | int | None]:
    if not rows:
        return {"bets": 0, "pnl_units": None, "roi": None}
    pnl = 0.0
    for row in rows:
        index = _top_index(selector(row))
        won = CLASS_ORDER[index] == row.result
        pnl += (row.odds[index] - 1.0) if won else -1.0
    return {
        "bets": len(rows),
        "pnl_units": pnl,
        "roi": pnl / len(rows),
    }


def _group_report(rows: list[DisagreementRow]) -> dict[str, object]:
    market = _metrics(rows, lambda row: row.market_probs)
    shadow = _metrics(rows, lambda row: row.shadow_mean_probs)
    blend = _metrics(rows, lambda row: row.blended_probs)
    return {
        "matches": len(rows),
        "market": market,
        "equal_shadow_mean": shadow,
        "market_90_shadow_10": blend,
        "blend_minus_market": {
            "log_loss": (
                float(blend["log_loss"]) - float(market["log_loss"])
                if blend["log_loss"] is not None and market["log_loss"] is not None
                else None
            ),
            "brier": (
                float(blend["brier"]) - float(market["brier"])
                if blend["brier"] is not None and market["brier"] is not None
                else None
            ),
        },
        "blind_one_unit_top_pick": {
            "market": _blind_top_roi(rows, lambda row: row.market_probs),
            "equal_shadow_mean": _blind_top_roi(
                rows, lambda row: row.shadow_mean_probs
            ),
            "market_90_shadow_10": _blind_top_roi(
                rows, lambda row: row.blended_probs
            ),
        },
        "mean_probability_dispersion": (
            sum(row.probability_dispersion for row in rows) / len(rows)
            if rows
            else None
        ),
        "mean_abs_shadow_market_distance": (
            sum(row.mean_abs_shadow_market_distance for row in rows) / len(rows)
            if rows
            else None
        ),
    }


def build_disagreement_rows(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
) -> list[DisagreementRow]:
    feature_rows = build_feature_rows(db_path)
    elo_rows = build_elo_rows(db_path)
    bayesian_rows = build_bayesian_strength_rows(db_path)
    scoreline_rows = build_scoreline_history(db_path)
    dixon_matches = load_matches(db_path)

    feature_by_match = {row.match_id: row for row in feature_rows}
    elo_by_match = {row.match_id: row for row in elo_rows}
    bayes_by_match = {row.match_id: row for row in bayesian_rows}
    scoreline_by_match = {row.match_id: row for row in scoreline_rows}
    dixon_by_match = {row.match_id: row for row in dixon_matches}

    seasons = sorted({row.season_start_year for row in feature_rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    result: list[DisagreementRow] = []
    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train_seasons = set(seasons[:test_index])

        elo_train = [
            row for row in elo_rows if row.season_start_year in train_seasons
        ]
        bayes_train = [
            row for row in bayesian_rows if row.season_start_year in train_seasons
        ]
        dixon_train = [
            row for row in dixon_matches if row.season_start_year in train_seasons
        ]
        elo_model = _fit_elo_probability_layer(elo_train)
        bayes_model = _fit_bayesian_probability_layer(
            bayes_train, include_regime=False
        )
        dixon_model = fit_dixon_coles(dixon_train)

        test_features = [
            row for row in feature_rows if row.season_start_year == test_season
        ]
        for feature in test_features:
            odds = _odds(feature)
            elo_row: EloRow | None = elo_by_match.get(feature.match_id)
            bayes_row: BayesianStrengthRow | None = bayes_by_match.get(
                feature.match_id
            )
            scoreline_row: ScorelineRow | None = scoreline_by_match.get(
                feature.match_id
            )
            dixon_match: MatchRecord | None = dixon_by_match.get(feature.match_id)
            if (
                odds is None
                or elo_row is None
                or bayes_row is None
                or scoreline_row is None
                or dixon_match is None
                or elo_row.market_probs is None
            ):
                continue

            market = elo_row.market_probs
            elo_probs = _predict_elo_probs(elo_model, elo_row)
            bayes_probs = _predict_bayesian_probs(
                bayes_model, bayes_row, include_regime=False
            )
            poisson_probs = (
                scoreline_row.home_prob,
                scoreline_row.draw_prob,
                scoreline_row.away_prob,
            )
            dixon_prediction = predict_dixon_coles_match(dixon_model, dixon_match)
            dixon_probs = (
                dixon_prediction.home_prob,
                dixon_prediction.draw_prob,
                dixon_prediction.away_prob,
            )
            shadow_probs = {
                "elo": elo_probs,
                "bayesian_strength": bayes_probs,
                "poisson": poisson_probs,
                "dixon_coles": dixon_probs,
            }
            shadow_values = [shadow_probs[name] for name in SHADOW_NAMES]
            shadow_mean = _mean_probs(shadow_values)
            blended = _blend(market, shadow_mean)

            top_indices = [_top_index(probs) for probs in shadow_values]
            counts = [top_indices.count(index) for index in range(3)]
            consensus_count = max(counts)
            consensus_candidates = [
                index for index, count in enumerate(counts) if count == consensus_count
            ]
            consensus_index = (
                consensus_candidates[0] if len(consensus_candidates) == 1 else None
            )
            market_top_index = _top_index(market)
            alignment_count = sum(
                1 for index in top_indices if index == market_top_index
            )

            array = np.asarray(shadow_values, dtype=float)
            dispersion = float(array.std(axis=0).mean())
            distance = float(np.mean(np.abs(array - np.asarray(market))))
            result.append(
                DisagreementRow(
                    match_id=feature.match_id,
                    season_start_year=feature.season_start_year,
                    match_date=feature.match_date,
                    home_team=feature.home_team,
                    away_team=feature.away_team,
                    result=feature.result,
                    market_probs=market,
                    odds=odds,
                    shadow_probs=shadow_probs,
                    shadow_mean_probs=shadow_mean,
                    blended_probs=blended,
                    market_top=CLASS_ORDER[market_top_index],
                    shadow_consensus_top=(
                        CLASS_ORDER[consensus_index]
                        if consensus_index is not None
                        else None
                    ),
                    shadow_consensus_count=consensus_count,
                    market_alignment_count=alignment_count,
                    probability_dispersion=dispersion,
                    mean_abs_shadow_market_distance=distance,
                )
            )
    return result


def model_disagreement_audit(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
) -> dict[str, object]:
    rows = build_disagreement_rows(
        db_path, min_train_seasons=min_train_seasons
    )
    groups = {
        "all_oos": rows,
        "all_four_shadows_agree_with_market": [
            row for row in rows if row.market_alignment_count == 4
        ],
        "three_shadows_agree_with_market": [
            row for row in rows if row.market_alignment_count == 3
        ],
        "two_or_fewer_shadows_agree_with_market": [
            row for row in rows if row.market_alignment_count <= 2
        ],
        "all_four_shadows_same_top_outcome": [
            row for row in rows if row.shadow_consensus_count == 4
        ],
        "all_four_shadows_same_and_market_agrees": [
            row
            for row in rows
            if row.shadow_consensus_count == 4 and row.market_alignment_count == 4
        ],
        "all_four_shadows_same_but_market_disagrees": [
            row
            for row in rows
            if row.shadow_consensus_count == 4 and row.market_alignment_count == 0
        ],
        "three_of_four_shadows_same_top_outcome": [
            row for row in rows if row.shadow_consensus_count == 3
        ],
        "shadows_split_two_two_or_weaker": [
            row for row in rows if row.shadow_consensus_count <= 2
        ],
    }
    season_reports = []
    for season in sorted({row.season_start_year for row in rows}):
        season_rows = [row for row in rows if row.season_start_year == season]
        season_reports.append(
            {
                "test_season_start_year": season,
                "report": _group_report(season_rows),
                "alignment_counts": {
                    str(k): sum(
                        1 for row in season_rows if row.market_alignment_count == k
                    )
                    for k in range(5)
                },
            }
        )

    strongest_disagreements = sorted(
        rows,
        key=lambda row: -row.mean_abs_shadow_market_distance,
    )[:25]
    return {
        "experiment": "shadow_model_disagreement_observer_v1",
        "status": "observer_only_zero_decision_weight",
        "shadow_models": list(SHADOW_NAMES),
        "model_policy": {
            "elo": "probability calibration fit only on seasons before each held-out season",
            "bayesian_strength": "dynamic leakage-safe state; probability calibration fit only on seasons before each held-out season",
            "poisson": "existing leakage-safe rolling pre-match expected-goals model",
            "dixon_coles": "fit only on seasons before each held-out season",
        },
        "blend_policy": (
            "predeclared descriptive challenger only: 90% de-vigged B365 market + 10% equal-weight mean of four shadow probabilities; no OOS tuning"
        ),
        "group_policy": (
            "agreement groups use only discrete top-outcome vote counts (4, 3, or <=2); no thresholds selected from outcomes"
        ),
        "interpretation_warning": (
            "Agreement can be evidence about uncertainty without being evidence of value. Blind top-pick ROI is descriptive and is not a staking rule."
        ),
        "groups": {name: _group_report(group) for name, group in groups.items()},
        "seasons": season_reports,
        "strongest_market_shadow_disagreements": [
            {
                "match_id": row.match_id,
                "season_start_year": row.season_start_year,
                "match_date": row.match_date,
                "home_team": row.home_team,
                "away_team": row.away_team,
                "result": row.result,
                "market_top": row.market_top,
                "shadow_consensus_top": row.shadow_consensus_top,
                "shadow_consensus_count": row.shadow_consensus_count,
                "market_alignment_count": row.market_alignment_count,
                "market_probs": row.market_probs,
                "shadow_mean_probs": row.shadow_mean_probs,
                "blended_probs": row.blended_probs,
                "mean_abs_shadow_market_distance": row.mean_abs_shadow_market_distance,
                "probability_dispersion": row.probability_dispersion,
            }
            for row in strongest_disagreements
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Observe whether agreement/disagreement among Football 1 shadow models carries OOS information."
    )
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/football1.sqlite")
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = model_disagreement_audit(
        args.database, min_train_seasons=args.min_train_seasons
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote model-disagreement report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
