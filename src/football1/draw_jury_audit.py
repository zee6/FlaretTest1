from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from sklearn.metrics import roc_auc_score

from football1.correlated_score import fit_dependence, load_actual_scores, predict_row
from football1.davidson import (
    fit_davidson,
    load_matches as load_davidson_matches,
    predict_match as predict_davidson_match,
)
from football1.dixon_coles import (
    fit_dixon_coles,
    load_matches as load_dixon_matches,
    predict_match as predict_dixon_match,
)
from football1.features import build_feature_rows
from football1.market_baseline import score_probabilities
from football1.random_forest_residual import (
    DEFAULT_RESIDUAL_WEIGHT,
    _fit_model as fit_rf,
    _market_probs as rf_market_probs,
    _probabilities_in_hda as rf_probabilities,
    geometric_market_correction,
    random_forest_vector,
)
from football1.scoreline import build_scoreline_history


JURORS = (
    "market",
    "independent_poisson",
    "dixon_coles",
    "davidson",
    "bivariate_poisson",
    "gamma_frailty",
    "market_plus_fixed_rf_residual",
)
FOOTBALL_JURORS = tuple(name for name in JURORS if name != "market")
EPS = 1e-12


def _score_category(home_goals: int, away_goals: int) -> str:
    if home_goals != away_goals:
        return "non_draw"
    if home_goals == 0:
        return "0-0"
    if home_goals == 1:
        return "1-1"
    if home_goals == 2:
        return "2-2"
    return "other_draw"


def _binary_draw_metrics(items: list[tuple[float, bool]]) -> dict[str, Any]:
    if not items:
        return {
            "matches": 0,
            "draws": 0,
            "draw_rate": None,
            "mean_predicted_draw_probability": None,
            "draw_brier": None,
            "draw_log_loss": None,
            "draw_auc": None,
            "mean_probability_on_actual_draws": None,
            "mean_probability_on_non_draws": None,
            "top_10pct": None,
            "top_20pct": None,
            "calibration_quintiles": [],
            "calibration_ece": None,
        }

    n = len(items)
    draws = sum(1 for _, actual in items if actual)
    base_rate = draws / n
    mean_p = sum(p for p, _ in items) / n
    brier = sum((p - float(actual)) ** 2 for p, actual in items) / n
    log_loss = -sum(
        math.log(min(1.0 - EPS, max(EPS, p))) if actual
        else math.log(min(1.0 - EPS, max(EPS, 1.0 - p)))
        for p, actual in items
    ) / n

    positive = [p for p, actual in items if actual]
    negative = [p for p, actual in items if not actual]
    auc = (
        float(roc_auc_score([int(actual) for _, actual in items], [p for p, _ in items]))
        if positive and negative
        else None
    )

    ranked = sorted(items, key=lambda x: x[0], reverse=True)

    def top_block(fraction: float) -> dict[str, Any]:
        count = max(1, math.ceil(n * fraction))
        selected = ranked[:count]
        observed = sum(1 for _, actual in selected if actual) / count
        return {
            "matches": count,
            "mean_predicted_draw_probability": sum(p for p, _ in selected) / count,
            "observed_draw_rate": observed,
            "lift_vs_base_rate": observed / base_rate if base_rate > 0 else None,
        }

    calibration: list[dict[str, Any]] = []
    ordered = sorted(items, key=lambda x: x[0])
    for quintile in range(5):
        lo = math.floor(n * quintile / 5)
        hi = math.floor(n * (quintile + 1) / 5)
        bucket = ordered[lo:hi]
        if not bucket:
            continue
        calibration.append(
            {
                "quintile": quintile + 1,
                "matches": len(bucket),
                "min_probability": min(p for p, _ in bucket),
                "max_probability": max(p for p, _ in bucket),
                "mean_predicted_probability": sum(p for p, _ in bucket) / len(bucket),
                "observed_draw_rate": sum(1 for _, actual in bucket if actual) / len(bucket),
            }
        )
    ece = sum(
        block["matches"] / n
        * abs(block["mean_predicted_probability"] - block["observed_draw_rate"])
        for block in calibration
    )

    return {
        "matches": n,
        "draws": draws,
        "draw_rate": base_rate,
        "mean_predicted_draw_probability": mean_p,
        "draw_brier": brier,
        "draw_log_loss": log_loss,
        "draw_auc": auc,
        "mean_probability_on_actual_draws": sum(positive) / len(positive) if positive else None,
        "mean_probability_on_non_draws": sum(negative) / len(negative) if negative else None,
        "top_10pct": top_block(0.10),
        "top_20pct": top_block(0.20),
        "calibration_quintiles": calibration,
        "calibration_ece": ece,
    }


def _multiclass_metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, Any]:
    if not items:
        return {"matches": 0, "log_loss": None, "brier": None, "accuracy": None}
    scores = [score_probabilities(probabilities, result) for probabilities, result in items]
    n = len(scores)
    return {
        "matches": n,
        "log_loss": sum(score.log_loss for score in scores) / n,
        "brier": sum(score.brier for score in scores) / n,
        "accuracy": sum(score.correct for score in scores) / n,
    }


def _top_set(rows: list[dict[str, Any]], juror: str, fraction: float = 0.20) -> set[str]:
    count = max(1, math.ceil(len(rows) * fraction))
    ranked = sorted(rows, key=lambda row: row["probabilities"][juror][1], reverse=True)
    return {str(row["match_id"]) for row in ranked[:count]}


def _top_quintile_jaccard(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    sets = {juror: _top_set(rows, juror) for juror in JURORS}
    result: dict[str, dict[str, float]] = {}
    for left in JURORS:
        result[left] = {}
        for right in JURORS:
            union = sets[left] | sets[right]
            result[left][right] = len(sets[left] & sets[right]) / len(union) if union else 1.0
    return result


def _build_prediction_maps(
    db_path: Path,
    *,
    min_train_seasons: int,
) -> tuple[list[dict[str, Any]], list[int]]:
    score_rows = build_scoreline_history(db_path)
    score_by_id = {row.match_id: row for row in score_rows}
    scores = load_actual_scores(db_path)
    seasons = sorted({row.season_start_year for row in score_rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for draw jury audit")
    test_seasons = seasons[min_train_seasons:]

    dixon_matches = load_dixon_matches(db_path)
    dixon_by_season: dict[int, list[Any]] = defaultdict(list)
    for match in dixon_matches:
        dixon_by_season[match.season_start_year].append(match)

    davidson_matches = load_davidson_matches(db_path)
    davidson_by_season: dict[int, list[Any]] = defaultdict(list)
    for match in davidson_matches:
        davidson_by_season[match.season_start_year].append(match)

    feature_rows = [
        row
        for row in build_feature_rows(db_path)
        if row.b365_home is not None and row.b365_draw is not None and row.b365_away is not None
    ]
    features_by_season: dict[int, list[Any]] = defaultdict(list)
    for row in feature_rows:
        features_by_season[row.season_start_year].append(row)

    predictions: dict[str, dict[str, tuple[float, float, float]]] = defaultdict(dict)

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        earlier = set(seasons[:test_index])

        dixon_train = [m for m in dixon_matches if m.season_start_year in earlier]
        dixon_model = fit_dixon_coles(dixon_train)
        for match in dixon_by_season[test_season]:
            pred = predict_dixon_match(dixon_model, match)
            predictions[match.match_id]["dixon_coles"] = (
                pred.home_prob,
                pred.draw_prob,
                pred.away_prob,
            )

        davidson_train = [m for m in davidson_matches if m.season_start_year in earlier]
        davidson_model = fit_davidson(davidson_train)
        for match in davidson_by_season[test_season]:
            pred = predict_davidson_match(davidson_model, match)
            predictions[match.match_id]["davidson"] = (
                pred.home_prob,
                pred.draw_prob,
                pred.away_prob,
            )

        dependence_train = [row for row in score_rows if row.season_start_year in earlier]
        dependence_fit = fit_dependence(dependence_train, scores)
        for row in score_rows:
            if row.season_start_year != test_season:
                continue
            pred = predict_row(row, dependence_fit)
            predictions[row.match_id]["bivariate_poisson"] = pred.bivariate_probs
            predictions[row.match_id]["gamma_frailty"] = pred.frailty_probs

        rf_train = [row for row in feature_rows if row.season_start_year in earlier]
        rf_model = fit_rf(rf_train)
        for row in features_by_season[test_season]:
            market = rf_market_probs(row)
            candidate = rf_probabilities(rf_model, random_forest_vector(row))
            corrected = geometric_market_correction(
                market,
                candidate,
                weight=DEFAULT_RESIDUAL_WEIGHT,
            )
            predictions[row.match_id]["market_plus_fixed_rf_residual"] = corrected

    common_rows: list[dict[str, Any]] = []
    for match_id, row in score_by_id.items():
        if row.season_start_year not in test_seasons or row.market_probs is None:
            continue
        entry = predictions.get(match_id, {})
        if any(
            juror not in entry
            for juror in FOOTBALL_JURORS
            if juror != "independent_poisson"
        ):
            continue
        actual_score = scores[match_id]
        probs = {
            "market": row.market_probs,
            "independent_poisson": (row.home_prob, row.draw_prob, row.away_prob),
            **entry,
        }
        if any(
            len(probabilities) != 3
            or not math.isclose(sum(probabilities), 1.0, abs_tol=1e-7)
            or any((not math.isfinite(p)) or p <= 0.0 or p >= 1.0 for p in probabilities)
            for probabilities in probs.values()
        ):
            raise ValueError(f"Invalid probability vector for {match_id}")
        common_rows.append(
            {
                "match_id": match_id,
                "season_start_year": row.season_start_year,
                "match_date": row.match_date,
                "home_team": row.home_team,
                "away_team": row.away_team,
                "result": row.result,
                "home_goals": actual_score[0],
                "away_goals": actual_score[1],
                "score_category": _score_category(*actual_score),
                "probabilities": probs,
            }
        )
    common_rows.sort(key=lambda row: (row["match_date"], row["match_id"]))
    return common_rows, test_seasons


def draw_jury_audit(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
) -> dict[str, Any]:
    rows, test_seasons = _build_prediction_maps(
        db_path,
        min_train_seasons=min_train_seasons,
    )
    if not rows:
        raise ValueError("No common paired rows for draw jury audit")

    juror_reports: dict[str, Any] = {}
    for juror in JURORS:
        draw_items = [
            (float(row["probabilities"][juror][1]), row["result"] == "D")
            for row in rows
        ]
        multiclass_items = [
            (tuple(row["probabilities"][juror]), str(row["result"]))
            for row in rows
        ]
        per_season: dict[str, Any] = {}
        for season in test_seasons:
            subset = [row for row in rows if row["season_start_year"] == season]
            if not subset:
                continue
            per_season[str(season)] = _binary_draw_metrics(
                [
                    (float(row["probabilities"][juror][1]), row["result"] == "D")
                    for row in subset
                ]
            )

        scoreline_draws: dict[str, Any] = {}
        for category in ("0-0", "1-1", "2-2", "other_draw"):
            subset = [row for row in rows if row["score_category"] == category]
            scoreline_draws[category] = {
                "matches": len(subset),
                "mean_predicted_draw_probability": (
                    sum(float(row["probabilities"][juror][1]) for row in subset) / len(subset)
                    if subset
                    else None
                ),
            }

        juror_reports[juror] = {
            "draw": _binary_draw_metrics(draw_items),
            "multiclass_context": _multiclass_metrics(multiclass_items),
            "actual_draw_scoreline_breakdown": scoreline_draws,
            "seasons": per_season,
        }

    actual_draws = [row for row in rows if row["result"] == "D"]
    score_counts: dict[str, int] = defaultdict(int)
    for row in actual_draws:
        score_counts[row["score_category"]] += 1

    football_consensus = []
    for row in rows:
        average_draw = sum(
            float(row["probabilities"][juror][1]) for juror in FOOTBALL_JURORS
        ) / len(FOOTBALL_JURORS)
        football_consensus.append((average_draw, row))
    football_consensus.sort(key=lambda item: item[0], reverse=True)

    examples = []
    for average_draw, row in football_consensus[:25]:
        examples.append(
            {
                "match_id": row["match_id"],
                "date": row["match_date"],
                "fixture": f'{row["home_team"]} vs {row["away_team"]}',
                "actual": row["result"],
                "score": f'{row["home_goals"]}-{row["away_goals"]}',
                "football_jury_mean_draw_probability": average_draw,
                "market_draw_probability": row["probabilities"]["market"][1],
                "juror_draw_probabilities": {
                    juror: row["probabilities"][juror][1] for juror in JURORS
                },
            }
        )

    return {
        "experiment": "draw_jury_historical_diagnostic_v1",
        "status": "historical_exploratory_previously_observed_data",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "warning": (
            "This audit diagnoses existing draw models on historical data that has already been inspected. "
            "It is not fresh confirmation of predictive or betting edge and must not be used to choose a betting rule."
        ),
        "sample_policy": (
            "Strict common paired sample across all jurors. Fitted jurors use season walk-forward: "
            "each held-out season is fit only on earlier seasons. The independent Poisson scoreline state "
            "is frozen before each match date; no same-date result updates another fixture on that date."
        ),
        "market": "de-vigged Bet365 pre-closing 1X2",
        "min_train_seasons": min_train_seasons,
        "test_seasons": test_seasons,
        "common_matches": len(rows),
        "actual_draws": len(actual_draws),
        "actual_draw_rate": len(actual_draws) / len(rows),
        "actual_draw_scoreline_counts": dict(score_counts),
        "jurors": juror_reports,
        "top_quintile_jaccard": _top_quintile_jaccard(rows),
        "highest_football_jury_draw_matches": examples,
        "interpretation_rules": {
            "draw_brier": "lower is better",
            "draw_log_loss": "lower is better",
            "draw_auc": "higher is better; 0.5 is random ranking",
            "calibration_ece": "lower is better",
            "top_20pct_lift": "higher means the juror concentrates actual draws into its most draw-prone fifth",
            "jaccard": "1 means identical top draw-prone fifths; 0 means no overlap",
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Historical diagnostic audit of Football 1's existing draw-probability jury."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/processed/football1.sqlite"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = draw_jury_audit(
        args.database,
        min_train_seasons=args.min_train_seasons,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote draw jury audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
