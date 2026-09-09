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

from football1.features import build_feature_rows
from football1.market_baseline import devig_decimal_odds


EPS = 1e-12
MIN_TRAIN_SEASONS = 4


def _row_from_feature(row: Any) -> dict[str, Any] | None:
    if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
        return None
    probs, _ = devig_decimal_odds(
        (float(row.b365_home), float(row.b365_draw), float(row.b365_away))
    )
    p_home, p_draw, p_away = probs
    return {
        "match_id": str(row.match_id),
        "season_start_year": int(row.season_start_year),
        "match_date": str(row.match_date),
        "is_draw": str(row.result) == "D",
        "p_draw": float(p_draw),
        "home_away_gap": abs(float(p_home) - float(p_away)),
    }


def _metrics(items: list[tuple[float, bool]]) -> dict[str, Any]:
    if not items:
        return {
            "matches": 0,
            "draws": 0,
            "draw_rate": None,
            "mean_probability": None,
            "brier": None,
            "log_loss": None,
            "auc": None,
            "ece": None,
        }
    n = len(items)
    draws = sum(int(actual) for _, actual in items)
    mean_probability = sum(float(p) for p, _ in items) / n
    brier = sum((float(p) - float(actual)) ** 2 for p, actual in items) / n
    log_loss = -sum(
        math.log(min(1.0 - EPS, max(EPS, float(p)))) if actual
        else math.log(min(1.0 - EPS, max(EPS, 1.0 - float(p))))
        for p, actual in items
    ) / n
    auc = None
    if 0 < draws < n:
        auc = float(roc_auc_score([int(actual) for _, actual in items], [float(p) for p, _ in items]))

    ordered = sorted(items, key=lambda item: float(item[0]))
    buckets: list[tuple[int, float, float]] = []
    for index in range(5):
        lo = math.floor(index * n / 5)
        hi = math.floor((index + 1) * n / 5)
        bucket = ordered[lo:hi]
        if bucket:
            buckets.append(
                (
                    len(bucket),
                    sum(float(p) for p, _ in bucket) / len(bucket),
                    sum(int(actual) for _, actual in bucket) / len(bucket),
                )
            )
    ece = sum(count / n * abs(mean_p - observed) for count, mean_p, observed in buckets)
    return {
        "matches": n,
        "draws": draws,
        "draw_rate": draws / n,
        "mean_probability": mean_probability,
        "brier": brier,
        "log_loss": log_loss,
        "auc": auc,
        "ece": ece,
    }


def _fit(features: list[list[float]], targets: list[int]) -> Pipeline:
    model = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "logistic",
                LogisticRegression(
                    C=1.0,
                    solver="lbfgs",
                    max_iter=2000,
                    random_state=31,
                ),
            ),
        ]
    )
    model.fit(features, targets)
    return model


def _delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("brier", "log_loss", "auc", "ece"):
        if left[key] is None or right[key] is None:
            result[key] = None
        else:
            result[key] = float(left[key]) - float(right[key])
    return result


def audit_minimal_draw_balance(
    db_path: Path,
    *,
    min_train_seasons: int = MIN_TRAIN_SEASONS,
) -> dict[str, Any]:
    rows = [x for raw in build_feature_rows(db_path) if (x := _row_from_feature(raw)) is not None]
    seasons = sorted({int(row["season_start_year"]) for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for chronological minimal draw balance audit")

    market_items: list[tuple[float, bool]] = []
    pdraw_only_items: list[tuple[float, bool]] = []
    pdraw_gap_items: list[tuple[float, bool]] = []
    season_reports: dict[str, Any] = {}
    latest_gap_model: Pipeline | None = None

    test_seasons = seasons[min_train_seasons:]
    for test_season in test_seasons:
        train = [row for row in rows if int(row["season_start_year"]) < test_season]
        test = [row for row in rows if int(row["season_start_year"]) == test_season]
        if not train or not test:
            continue

        y_train = [int(row["is_draw"]) for row in train]
        pdraw_only = _fit([[float(row["p_draw"])] for row in train], y_train)
        pdraw_gap = _fit(
            [[float(row["p_draw"]), float(row["home_away_gap"])] for row in train],
            y_train,
        )
        latest_gap_model = pdraw_gap

        pdraw_only_probs = pdraw_only.predict_proba([[float(row["p_draw"])] for row in test])[:, 1]
        pdraw_gap_probs = pdraw_gap.predict_proba(
            [[float(row["p_draw"]), float(row["home_away_gap"])] for row in test]
        )[:, 1]

        season_market: list[tuple[float, bool]] = []
        season_pdraw: list[tuple[float, bool]] = []
        season_gap: list[tuple[float, bool]] = []
        for row, p_only, p_gap in zip(test, pdraw_only_probs, pdraw_gap_probs, strict=True):
            actual = bool(row["is_draw"])
            market_pair = (float(row["p_draw"]), actual)
            pdraw_pair = (float(p_only), actual)
            gap_pair = (float(p_gap), actual)
            market_items.append(market_pair)
            pdraw_only_items.append(pdraw_pair)
            pdraw_gap_items.append(gap_pair)
            season_market.append(market_pair)
            season_pdraw.append(pdraw_pair)
            season_gap.append(gap_pair)

        market_metrics = _metrics(season_market)
        pdraw_metrics = _metrics(season_pdraw)
        gap_metrics = _metrics(season_gap)
        season_reports[str(test_season)] = {
            "market_raw_pdraw": market_metrics,
            "pdraw_only_recalibration": pdraw_metrics,
            "pdraw_plus_home_away_gap": gap_metrics,
            "delta_gap_minus_pdraw_only": _delta(gap_metrics, pdraw_metrics),
            "delta_gap_minus_market": _delta(gap_metrics, market_metrics),
        }

    if latest_gap_model is None or not pdraw_gap_items:
        raise ValueError("No OOS predictions produced")

    market_metrics = _metrics(market_items)
    pdraw_metrics = _metrics(pdraw_only_items)
    gap_metrics = _metrics(pdraw_gap_items)
    logistic = latest_gap_model.named_steps["logistic"]
    coefficients = {
        "market_draw_probability": float(logistic.coef_[0][0]),
        "home_away_probability_gap": float(logistic.coef_[0][1]),
    }

    season_deltas = [
        report["delta_gap_minus_pdraw_only"]
        for report in season_reports.values()
    ]
    return {
        "experiment": "minimal_draw_balance_incremental_walk_forward_v1",
        "status": "historical_post_hoc_zero_decision_weight",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "question": (
            "Does absolute H/A market-probability balance add incremental draw information "
            "beyond the bookmaker market's own draw probability?"
        ),
        "design": {
            "chronology": "expanding walk-forward by season; each test season is predicted using earlier seasons only",
            "min_train_seasons": min_train_seasons,
            "test_seasons": test_seasons,
            "market_control": "raw de-vigged B365 pre-closing draw probability",
            "calibration_control": "logistic regression using market draw probability only",
            "candidate": "same logistic regression plus absolute de-vigged market H/A probability gap",
            "hyperparameter_status": "fixed before this audit; no threshold or regularization search",
        },
        "oos_matches": len(pdraw_gap_items),
        "market_raw_pdraw": market_metrics,
        "pdraw_only_recalibration": pdraw_metrics,
        "pdraw_plus_home_away_gap": gap_metrics,
        "delta_gap_minus_pdraw_only": _delta(gap_metrics, pdraw_metrics),
        "delta_gap_minus_market": _delta(gap_metrics, market_metrics),
        "season_stability": {
            "seasons": len(season_reports),
            "gap_improves_brier_vs_pdraw_only": sum(
                1 for delta in season_deltas if delta["brier"] is not None and delta["brier"] < 0
            ),
            "gap_improves_log_loss_vs_pdraw_only": sum(
                1 for delta in season_deltas if delta["log_loss"] is not None and delta["log_loss"] < 0
            ),
            "gap_improves_auc_vs_pdraw_only": sum(
                1 for delta in season_deltas if delta["auc"] is not None and delta["auc"] > 0
            ),
        },
        "latest_fit_standardized_coefficients": coefficients,
        "seasons": season_reports,
        "guardrails": [
            "This audit follows discovery of the draw-balance historical clue and is therefore post-hoc, not untouched validation.",
            "A negative coefficient on H/A gap would mean more balanced H/A win probabilities are associated with higher draw propensity after conditioning on market pDraw.",
            "No betting threshold, draw probability override, stake rule or product recommendation is created.",
            "Even an aggregate improvement must be judged for seasonal stability and then prospectively.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit incremental draw information in simple H/A market balance.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--min-train-seasons", type=int, default=MIN_TRAIN_SEASONS)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = audit_minimal_draw_balance(args.database, min_train_seasons=args.min_train_seasons)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote minimal draw balance audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
