from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from football1.draw_jury_audit import FOOTBALL_JURORS, _build_prediction_maps
from football1.features import build_feature_rows
from football1.scoreline import build_scoreline_history


MODEL_ID = "hybrid_draw_profile_logistic_v1"
DECISION_WEIGHT = 0.0
FEATURE_NAMES = (
    "market_draw_probability",
    "retained_rf_draw_probability",
    "rf_draw_residual_vs_market",
    "market_home_away_gap",
    "retained_rf_home_away_gap",
    "independent_poisson_draw_probability",
    "dixon_coles_draw_probability",
    "davidson_draw_probability",
    "bivariate_poisson_draw_probability",
    "gamma_frailty_draw_probability",
    "football_jury_draw_mean",
    "football_jury_draw_spread",
    "expected_goal_gap",
    "expected_goal_total",
    "low_score_draw_mass_0_to_2",
    "absolute_elo_difference",
)
EPS = 1e-12


def _poisson_probability(lam: float, goals: int) -> float:
    return math.exp(-lam) * (lam ** goals) / math.factorial(goals)


def low_score_draw_mass(lambda_home: float, lambda_away: float) -> float:
    """Independent-Poisson mass on 0-0, 1-1 and 2-2."""
    return sum(
        _poisson_probability(lambda_home, goals) * _poisson_probability(lambda_away, goals)
        for goals in (0, 1, 2)
    )


def _feature_vector(
    row: dict[str, Any],
    *,
    expected_home_goals: float,
    expected_away_goals: float,
    elo_diff: float,
) -> list[float]:
    probs = row["probabilities"]
    market = probs["market"]
    retained = probs["market_plus_fixed_rf_residual"]
    football_draws = [float(probs[juror][1]) for juror in FOOTBALL_JURORS]
    mean_draw = sum(football_draws) / len(football_draws)
    spread = max(football_draws) - min(football_draws)
    return [
        float(market[1]),
        float(retained[1]),
        float(retained[1] - market[1]),
        abs(float(market[0] - market[2])),
        abs(float(retained[0] - retained[2])),
        float(probs["independent_poisson"][1]),
        float(probs["dixon_coles"][1]),
        float(probs["davidson"][1]),
        float(probs["bivariate_poisson"][1]),
        float(probs["gamma_frailty"][1]),
        mean_draw,
        spread,
        abs(expected_home_goals - expected_away_goals),
        expected_home_goals + expected_away_goals,
        low_score_draw_mass(expected_home_goals, expected_away_goals),
        abs(elo_diff),
    ]


def _binary_metrics(items: list[tuple[float, bool]]) -> dict[str, Any]:
    if not items:
        return {
            "matches": 0,
            "positives": 0,
            "base_rate": None,
            "mean_probability": None,
            "brier": None,
            "log_loss": None,
            "auc": None,
            "calibration_ece": None,
            "top_20pct": None,
        }
    n = len(items)
    positives = sum(1 for _, actual in items if actual)
    base_rate = positives / n
    mean_probability = sum(p for p, _ in items) / n
    brier = sum((p - float(actual)) ** 2 for p, actual in items) / n
    log_loss = -sum(
        math.log(min(1.0 - EPS, max(EPS, p))) if actual
        else math.log(min(1.0 - EPS, max(EPS, 1.0 - p)))
        for p, actual in items
    ) / n
    auc = None
    if 0 < positives < n:
        auc = float(roc_auc_score([int(actual) for _, actual in items], [p for p, _ in items]))

    ordered = sorted(items, key=lambda pair: pair[0])
    calibration = []
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
                "mean_probability": sum(p for p, _ in bucket) / len(bucket),
                "observed_rate": sum(1 for _, actual in bucket if actual) / len(bucket),
            }
        )
    ece = sum(
        bucket["matches"] / n * abs(bucket["mean_probability"] - bucket["observed_rate"])
        for bucket in calibration
    )
    ranked = sorted(items, key=lambda pair: pair[0], reverse=True)
    count = max(1, math.ceil(n * 0.20))
    top = ranked[:count]
    top_rate = sum(1 for _, actual in top if actual) / count
    return {
        "matches": n,
        "positives": positives,
        "base_rate": base_rate,
        "mean_probability": mean_probability,
        "brier": brier,
        "log_loss": log_loss,
        "auc": auc,
        "calibration_ece": ece,
        "calibration_quintiles": calibration,
        "top_20pct": {
            "matches": count,
            "mean_probability": sum(p for p, _ in top) / count,
            "observed_rate": top_rate,
            "lift_vs_base_rate": top_rate / base_rate if base_rate > 0 else None,
        },
    }


def _fit_profile(train: list[dict[str, Any]]) -> Pipeline:
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "logistic",
                LogisticRegression(
                    C=0.25,
                    max_iter=2000,
                    solver="lbfgs",
                    random_state=23,
                ),
            ),
        ]
    )
    model.fit(
        [row["draw_profile_features"] for row in train],
        [1 if row["result"] == "D" else 0 for row in train],
    )
    return model


def _attach_features(db_path: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    score_by_id = {row.match_id: row for row in build_scoreline_history(db_path)}
    feature_by_id = {row.match_id: row for row in build_feature_rows(db_path)}
    enriched = []
    for row in rows:
        score = score_by_id.get(str(row["match_id"]))
        feature = feature_by_id.get(str(row["match_id"]))
        if score is None or feature is None:
            continue
        item = dict(row)
        item["draw_profile_features"] = _feature_vector(
            row,
            expected_home_goals=float(score.expected_home_goals),
            expected_away_goals=float(score.expected_away_goals),
            elo_diff=float(feature.elo_diff),
        )
        item["expected_home_goals"] = float(score.expected_home_goals)
        item["expected_away_goals"] = float(score.expected_away_goals)
        item["absolute_elo_difference"] = abs(float(feature.elo_diff))
        enriched.append(item)
    return enriched


def draw_profile_audit(
    db_path: Path,
    *,
    base_min_train_seasons: int = 3,
    profile_train_seasons: int = 2,
) -> dict[str, Any]:
    """Nested walk-forward audit of a transparent hybrid draw observer.

    Base juror probabilities are already out-of-sample by season. The hybrid
    observer is then trained only on earlier base-OOS seasons, creating a second
    chronological boundary rather than fitting a stacker on the same season it scores.
    """
    base_rows, base_test_seasons = _build_prediction_maps(
        db_path,
        min_train_seasons=base_min_train_seasons,
    )
    rows = _attach_features(db_path, base_rows)
    if len(base_test_seasons) <= profile_train_seasons:
        raise ValueError("Not enough base-OOS seasons for nested draw profile audit")

    profile_test_seasons = base_test_seasons[profile_train_seasons:]
    predictions: list[dict[str, Any]] = []
    season_reports: dict[str, Any] = {}
    latest_model: Pipeline | None = None

    for test_season in profile_test_seasons:
        earlier = set(season for season in base_test_seasons if season < test_season)
        train = [row for row in rows if row["season_start_year"] in earlier]
        test = [row for row in rows if row["season_start_year"] == test_season]
        if not train or not test:
            continue
        model = _fit_profile(train)
        latest_model = model
        probabilities = model.predict_proba([row["draw_profile_features"] for row in test])[:, 1]
        season_items = []
        market_items = []
        for row, probability in zip(test, probabilities):
            actual = row["result"] == "D"
            market_probability = float(row["probabilities"]["market"][1])
            season_items.append((float(probability), actual))
            market_items.append((market_probability, actual))
            predictions.append(
                {
                    "match_id": row["match_id"],
                    "season_start_year": row["season_start_year"],
                    "match_date": row["match_date"],
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "result": row["result"],
                    "score": f'{row["home_goals"]}-{row["away_goals"]}',
                    "profile_probability": float(probability),
                    "market_draw_probability": market_probability,
                    "retained_rf_draw_probability": float(
                        row["probabilities"]["market_plus_fixed_rf_residual"][1]
                    ),
                    "absolute_elo_difference": row["absolute_elo_difference"],
                    "expected_home_goals": row["expected_home_goals"],
                    "expected_away_goals": row["expected_away_goals"],
                }
            )
        season_reports[str(test_season)] = {
            "hybrid": _binary_metrics(season_items),
            "market": _binary_metrics(market_items),
        }

    if not predictions or latest_model is None:
        raise ValueError("No nested OOS draw profile predictions were produced")

    hybrid_items = [(row["profile_probability"], row["result"] == "D") for row in predictions]
    market_items = [(row["market_draw_probability"], row["result"] == "D") for row in predictions]
    hybrid_metrics = _binary_metrics(hybrid_items)
    market_metrics = _binary_metrics(market_items)

    logistic = latest_model.named_steps["logistic"]
    coefficients = {
        name: float(value)
        for name, value in zip(FEATURE_NAMES, logistic.coef_[0])
    }
    ranked_examples = sorted(predictions, key=lambda row: row["profile_probability"], reverse=True)[:25]

    non_loss = _non_loss_probability_audit(rows, profile_test_seasons)
    return {
        "experiment": "hybrid_draw_profile_nested_walk_forward_v1",
        "model_id": MODEL_ID,
        "status": "historical_exploratory_previously_observed_data",
        "decision_weight": DECISION_WEIGHT,
        "promotion_allowed": False,
        "interface_status": "under_hood_research_interface_deferred",
        "base_juror_oos_seasons": base_test_seasons,
        "nested_profile_test_seasons": profile_test_seasons,
        "oos_matches": len(predictions),
        "features": list(FEATURE_NAMES),
        "hybrid": hybrid_metrics,
        "market_control": market_metrics,
        "delta_hybrid_minus_market": {
            "brier": hybrid_metrics["brier"] - market_metrics["brier"],
            "log_loss": hybrid_metrics["log_loss"] - market_metrics["log_loss"],
            "auc": (
                hybrid_metrics["auc"] - market_metrics["auc"]
                if hybrid_metrics["auc"] is not None and market_metrics["auc"] is not None
                else None
            ),
        },
        "latest_oos_fit_standardized_coefficients": coefficients,
        "seasons": season_reports,
        "highest_draw_profile_matches": ranked_examples,
        "non_loss_probability_audit": non_loss,
        "warning": (
            "This hybrid was designed after inspection of prior Football 1 research and is evaluated "
            "on historical seasons already available to the project. It is diagnostic, not fresh proof. "
            "Any production weight, confidence label, threshold or staking rule requires a new frozen "
            "prospective protocol."
        ),
    }


def _non_loss_probability_audit(
    rows: list[dict[str, Any]],
    test_seasons: list[int],
) -> dict[str, Any]:
    eligible = [row for row in rows if row["season_start_year"] in set(test_seasons)]

    def items(kind: str, juror: str) -> list[tuple[float, bool]]:
        result = []
        for row in eligible:
            p = row["probabilities"][juror]
            if kind == "1X":
                probability = float(p[0] + p[1])
                actual = row["result"] != "A"
            elif kind == "X2":
                probability = float(p[1] + p[2])
                actual = row["result"] != "H"
            else:
                market = row["probabilities"]["market"]
                outsider = 0 if market[0] < market[2] else 2
                probability = float(p[1] + p[outsider])
                actual = row["result"] == "D" or (
                    row["result"] == "H" if outsider == 0 else row["result"] == "A"
                )
            result.append((probability, actual))
        return result

    report = {}
    for kind in ("1X", "X2", "market_outsider_or_draw"):
        model = _binary_metrics(items(kind, "market_plus_fixed_rf_residual"))
        market = _binary_metrics(items(kind, "market"))
        report[kind] = {
            "retained_rf": model,
            "market": market,
            "delta_rf_minus_market": {
                "brier": model["brier"] - market["brier"],
                "log_loss": model["log_loss"] - market["log_loss"],
            },
        }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the zero-weight hybrid draw/non-loss historical observer.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/draw_profile_audit.json"))
    parser.add_argument("--base-min-train-seasons", type=int, default=3)
    parser.add_argument("--profile-train-seasons", type=int, default=2)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = draw_profile_audit(
        args.database,
        base_min_train_seasons=args.base_min_train_seasons,
        profile_train_seasons=args.profile_train_seasons,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["delta_hybrid_minus_market"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
