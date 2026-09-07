from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from football1.features import FeatureRow, build_feature_rows
from football1.market_baseline import RESULT_INDEX, score_probabilities
from football1.offset_slant import _market_probs, fit_offset_slant


ALPHA = 0.10
MIN_TRAIN_SEASONS = 3
EPS = 1e-12
OUTCOME_LABELS = ("H", "D", "A")


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _quantile_reference(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {name: None for name in ("p50", "p75", "p90", "p95", "p99", "max")}
    ordered = sorted(values)

    def nearest_rank(q: float) -> float:
        index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
        return float(ordered[index])

    return {
        "p50": nearest_rank(0.50),
        "p75": nearest_rank(0.75),
        "p90": nearest_rank(0.90),
        "p95": nearest_rank(0.95),
        "p99": nearest_rank(0.99),
        "max": float(ordered[-1]),
    }


def _binary_log_loss(probability: float, actual: int) -> float:
    p = min(1.0 - EPS, max(EPS, float(probability)))
    return -math.log(p if actual else 1.0 - p)


def _multiclass_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "matches": 0,
            "mean_max_abs_residual": None,
            "mean_l1_residual": None,
            "market_log_loss": None,
            "model_log_loss": None,
            "log_loss_delta_model_minus_market": None,
            "market_brier": None,
            "model_brier": None,
            "brier_delta_model_minus_market": None,
        }

    market_scores = [score_probabilities(tuple(r["market_probability"]), str(r["result"])) for r in records]
    model_scores = [score_probabilities(tuple(r["model_probability"]), str(r["result"])) for r in records]
    n = len(records)
    market_ll = sum(s.log_loss for s in market_scores) / n
    model_ll = sum(s.log_loss for s in model_scores) / n
    market_brier = sum(s.brier for s in market_scores) / n
    model_brier = sum(s.brier for s in model_scores) / n
    return {
        "matches": n,
        "mean_max_abs_residual": sum(float(r["max_abs_residual"]) for r in records) / n,
        "mean_l1_residual": sum(float(r["l1_residual"]) for r in records) / n,
        "market_log_loss": market_ll,
        "model_log_loss": model_ll,
        "log_loss_delta_model_minus_market": model_ll - market_ll,
        "market_brier": market_brier,
        "model_brier": model_brier,
        "brier_delta_model_minus_market": model_brier - market_brier,
    }


def _selected_shift_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "matches": 0,
            "mean_positive_shift": None,
            "mean_market_probability": None,
            "mean_model_probability": None,
            "observed_rate": None,
            "observed_minus_market_expectation": None,
            "market_binary_log_loss": None,
            "model_binary_log_loss": None,
            "log_loss_delta_model_minus_market": None,
            "market_binary_brier": None,
            "model_binary_brier": None,
            "brier_delta_model_minus_market": None,
        }

    n = len(records)
    shifts = [float(r["selected_positive_shift"]) for r in records]
    market_p = [float(r["selected_market_probability"]) for r in records]
    model_p = [float(r["selected_model_probability"]) for r in records]
    actual = [int(r["selected_actual"]) for r in records]
    market_ll = sum(_binary_log_loss(p, y) for p, y in zip(market_p, actual)) / n
    model_ll = sum(_binary_log_loss(p, y) for p, y in zip(model_p, actual)) / n
    market_brier = sum((p - y) ** 2 for p, y in zip(market_p, actual)) / n
    model_brier = sum((p - y) ** 2 for p, y in zip(model_p, actual)) / n
    observed = sum(actual) / n
    mean_market = sum(market_p) / n
    return {
        "matches": n,
        "mean_positive_shift": sum(shifts) / n,
        "mean_market_probability": mean_market,
        "mean_model_probability": sum(model_p) / n,
        "observed_rate": observed,
        "observed_minus_market_expectation": observed - mean_market,
        "market_binary_log_loss": market_ll,
        "model_binary_log_loss": model_ll,
        "log_loss_delta_model_minus_market": model_ll - market_ll,
        "market_binary_brier": market_brier,
        "model_binary_brier": model_brier,
        "brier_delta_model_minus_market": model_brier - market_brier,
    }


def _quintile_blocks(
    records: list[dict[str, Any]],
    *,
    key: str,
    summarizer,
) -> list[dict[str, Any]]:
    if not records:
        return []
    ordered = sorted(records, key=lambda r: float(r[key]))
    n = len(ordered)
    blocks: list[dict[str, Any]] = []
    for quintile in range(5):
        lo = math.floor(n * quintile / 5)
        hi = math.floor(n * (quintile + 1) / 5)
        bucket = ordered[lo:hi]
        if not bucket:
            continue
        values = [float(r[key]) for r in bucket]
        blocks.append(
            {
                "quintile": quintile + 1,
                "min_value": min(values),
                "max_value": max(values),
                **summarizer(bucket),
            }
        )
    return blocks


def summarize_residual_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize already-OOS residual records without selecting a threshold."""
    per_season: dict[str, Any] = {}
    for season in sorted({int(r["season_start_year"]) for r in records}):
        subset = [r for r in records if int(r["season_start_year"]) == season]
        per_season[str(season)] = _multiclass_metrics(subset)

    per_outcome: dict[str, Any] = {}
    for index, label in enumerate(OUTCOME_LABELS):
        shifted = [
            r for r in records
            if int(r["selected_outcome_index"]) == index
        ]
        per_outcome[label] = _selected_shift_metrics(shifted)

    return {
        "matches": len(records),
        "overall": _multiclass_metrics(records),
        "reference_quantiles": {
            "match_max_abs_residual": _quantile_reference([float(r["max_abs_residual"]) for r in records]),
            "selected_positive_shift": _quantile_reference([float(r["selected_positive_shift"]) for r in records]),
        },
        "match_max_abs_residual_quintiles": _quintile_blocks(
            records,
            key="max_abs_residual",
            summarizer=_multiclass_metrics,
        ),
        "selected_positive_shift_quintiles": _quintile_blocks(
            records,
            key="selected_positive_shift",
            summarizer=_selected_shift_metrics,
        ),
        "selected_positive_shift_by_outcome": per_outcome,
        "seasons": per_season,
    }


def _eligible_rows(db_path: Path) -> list[FeatureRow]:
    return [
        row for row in build_feature_rows(db_path)
        if row.b365_home is not None and row.b365_draw is not None and row.b365_away is not None
    ]


def build_oos_residual_records(
    db_path: Path,
    *,
    min_train_seasons: int = MIN_TRAIN_SEASONS,
    alpha: float = ALPHA,
) -> tuple[list[dict[str, Any]], list[int]]:
    rows = _eligible_rows(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for residual magnitude audit")

    records: list[dict[str, Any]] = []
    test_seasons = seasons[min_train_seasons:]
    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        earlier = set(seasons[:test_index])
        train = [row for row in rows if row.season_start_year in earlier]
        test = [row for row in rows if row.season_start_year == test_season]
        model = fit_offset_slant(train, alpha=alpha)

        for row in test:
            market = _market_probs(row)
            candidate = model.predict_with_base(row, market)
            residual = tuple(candidate[i] - market[i] for i in range(3))
            selected_index = max(range(3), key=lambda i: residual[i])
            target = RESULT_INDEX[row.result]
            records.append(
                {
                    "match_id": row.match_id,
                    "season_start_year": row.season_start_year,
                    "match_date": row.match_date,
                    "result": row.result,
                    "market_probability": market,
                    "model_probability": candidate,
                    "probability_residual": residual,
                    "max_abs_residual": max(abs(value) for value in residual),
                    "l1_residual": sum(abs(value) for value in residual),
                    "selected_outcome_index": selected_index,
                    "selected_outcome": OUTCOME_LABELS[selected_index],
                    "selected_positive_shift": residual[selected_index],
                    "selected_market_probability": market[selected_index],
                    "selected_model_probability": candidate[selected_index],
                    "selected_actual": int(target == selected_index),
                }
            )

    records.sort(key=lambda r: (str(r["match_date"]), str(r["match_id"])))
    return records, test_seasons


def residual_magnitude_audit(
    db_path: Path,
    *,
    min_train_seasons: int = MIN_TRAIN_SEASONS,
    alpha: float = ALPHA,
) -> dict[str, Any]:
    records, test_seasons = build_oos_residual_records(
        db_path,
        min_train_seasons=min_train_seasons,
        alpha=alpha,
    )
    summary = summarize_residual_records(records)
    return {
        "experiment": "fixed_market_offset_residual_magnitude_audit_v1",
        "status": "historical_exploratory_previously_observed_data",
        "decision_weight": 0.0,
        "promotion_allowed": False,
        "model": "fixed_market_offset_football_slant_v1",
        "alpha": alpha,
        "market_anchor": "B365 pre-closing de-vigged",
        "split_policy": "walk-forward by season; each test season uses only earlier seasons for fitting",
        "test_seasons": test_seasons,
        "warning": (
            "This diagnostic asks whether larger historical Football 1 residuals were more reliable. "
            "It does not select a residual threshold and cannot provide fresh confirmation because these "
            "historical seasons have already been inspected. The prospective live anchor is a multi-book UK "
            "consensus rather than historical B365, so historical residual magnitudes are contextual only."
        ),
        **summary,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit whether larger Football 1 market residuals historically became more reliable."
    )
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/residual_magnitude_audit.json"))
    parser.add_argument("--min-train-seasons", type=int, default=MIN_TRAIN_SEASONS)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = residual_magnitude_audit(
        args.database,
        min_train_seasons=args.min_train_seasons,
        alpha=args.alpha,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "decision_weight": report["decision_weight"],
        "matches": report["matches"],
        "overall": report["overall"],
        "reference_quantiles": report["reference_quantiles"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
