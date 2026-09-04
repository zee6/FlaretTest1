from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from football1.features import FEATURE_NAMES, FeatureRow, build_feature_rows, feature_vector
from football1.market_baseline import devig_decimal_odds, score_probabilities


RESULTS = ("H", "D", "A")


def _mean_metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    if not items:
        return {"matches": 0, "log_loss": None, "brier": None, "accuracy": None}
    log_loss = brier = 0.0
    correct = 0
    for probs, result in items:
        score = score_probabilities(probs, result)
        log_loss += score.log_loss
        brier += score.brier
        correct += score.correct
    n = len(items)
    return {
        "matches": n,
        "log_loss": log_loss / n,
        "brier": brier / n,
        "accuracy": correct / n,
    }


def _probabilities_in_hda(model: Pipeline, vector: list[float]) -> tuple[float, float, float]:
    raw = model.predict_proba([vector])[0]
    classes = list(model.named_steps["model"].classes_)
    mapping = {label: float(raw[i]) for i, label in enumerate(classes)}
    return (mapping["H"], mapping["D"], mapping["A"])


def _top_label_ece(items: list[tuple[tuple[float, float, float], str]], bins: int = 10) -> float | None:
    if not items:
        return None
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for probs, result in items:
        predicted_index = max(range(3), key=lambda i: probs[i])
        confidence = probs[predicted_index]
        actual = 1 if RESULTS[predicted_index] == result else 0
        bucket = min(bins - 1, int(confidence * bins))
        buckets[bucket].append((confidence, actual))
    total = len(items)
    ece = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        mean_conf = sum(x[0] for x in bucket) / len(bucket)
        mean_acc = sum(x[1] for x in bucket) / len(bucket)
        ece += (len(bucket) / total) * abs(mean_conf - mean_acc)
    return ece


def _market_probs(row: FeatureRow) -> tuple[float, float, float] | None:
    if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
        return None
    return devig_decimal_odds((row.b365_home, row.b365_draw, row.b365_away))[0]


def walk_forward_baseline(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    c: float = 1.0,
) -> dict[str, object]:
    """Fit once per OOS season using only strictly earlier seasons.

    Features themselves are updated from earlier completed dates, but model
    parameters are frozen for the whole test season. This makes each reported
    season a clean, independently held-out OOS block.
    """
    rows = build_feature_rows(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for requested walk-forward evaluation")

    season_reports: list[dict[str, object]] = []
    all_model_items: list[tuple[tuple[float, float, float], str]] = []
    all_market_items: list[tuple[tuple[float, float, float], str]] = []
    paired_model_items: list[tuple[tuple[float, float, float], str]] = []
    paired_market_items: list[tuple[tuple[float, float, float], str]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        training_seasons = seasons[:test_index]
        train = [row for row in rows if row.season_start_year in training_seasons]
        test = [row for row in rows if row.season_start_year == test_season]

        x_train = [feature_vector(row) for row in train]
        y_train = [row.result for row in train]
        if set(y_train) != set(RESULTS):
            raise ValueError(f"Training block before {test_season} lacks all H/D/A classes")

        model = Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=c,
                        solver="lbfgs",
                        max_iter=3000,
                    ),
                ),
            ]
        )
        model.fit(x_train, y_train)

        model_items: list[tuple[tuple[float, float, float], str]] = []
        market_items: list[tuple[tuple[float, float, float], str]] = []
        paired_model: list[tuple[tuple[float, float, float], str]] = []
        paired_market: list[tuple[tuple[float, float, float], str]] = []

        for row in test:
            model_probs = _probabilities_in_hda(model, feature_vector(row))
            model_items.append((model_probs, row.result))
            all_model_items.append((model_probs, row.result))

            market_probs = _market_probs(row)
            if market_probs is not None:
                market_items.append((market_probs, row.result))
                all_market_items.append((market_probs, row.result))
                paired_model.append((model_probs, row.result))
                paired_market.append((market_probs, row.result))
                paired_model_items.append((model_probs, row.result))
                paired_market_items.append((market_probs, row.result))

        model_metrics = _mean_metrics(model_items)
        market_metrics = _mean_metrics(market_items)
        paired_model_metrics = _mean_metrics(paired_model)
        paired_market_metrics = _mean_metrics(paired_market)
        season_reports.append(
            {
                "test_season_start_year": test_season,
                "training_seasons": training_seasons,
                "train_matches": len(train),
                "test_matches": len(test),
                "model": {**model_metrics, "top_label_ece": _top_label_ece(model_items)},
                "market_b365_pre_closing": {
                    **market_metrics,
                    "top_label_ece": _top_label_ece(market_items),
                },
                "paired_comparison": {
                    "matches": int(paired_model_metrics["matches"]),
                    "model_log_loss": paired_model_metrics["log_loss"],
                    "market_log_loss": paired_market_metrics["log_loss"],
                    "log_loss_delta_model_minus_market": (
                        float(paired_model_metrics["log_loss"]) - float(paired_market_metrics["log_loss"])
                        if paired_model_metrics["log_loss"] is not None and paired_market_metrics["log_loss"] is not None
                        else None
                    ),
                    "model_brier": paired_model_metrics["brier"],
                    "market_brier": paired_market_metrics["brier"],
                    "brier_delta_model_minus_market": (
                        float(paired_model_metrics["brier"]) - float(paired_market_metrics["brier"])
                        if paired_model_metrics["brier"] is not None and paired_market_metrics["brier"] is not None
                        else None
                    ),
                },
            }
        )

    total_model = _mean_metrics(all_model_items)
    total_market = _mean_metrics(all_market_items)
    total_paired_model = _mean_metrics(paired_model_items)
    total_paired_market = _mean_metrics(paired_market_items)
    return {
        "model": "multinomial_logistic_football_only_v1",
        "feature_names": list(FEATURE_NAMES),
        "market_features_used": False,
        "split_policy": "walk-forward by season; model fit only on earlier seasons; features use only earlier dates",
        "same_day_policy": "all fixtures on one date snapshotted before any result from that date updates team state",
        "min_train_seasons": min_train_seasons,
        "regularization_C": c,
        "overall_model": {**total_model, "top_label_ece": _top_label_ece(all_model_items)},
        "overall_market_b365_pre_closing": {
            **total_market,
            "top_label_ece": _top_label_ece(all_market_items),
        },
        "paired_overall": {
            "matches": int(total_paired_model["matches"]),
            "model_log_loss": total_paired_model["log_loss"],
            "market_log_loss": total_paired_market["log_loss"],
            "log_loss_delta_model_minus_market": (
                float(total_paired_model["log_loss"]) - float(total_paired_market["log_loss"])
                if total_paired_model["log_loss"] is not None and total_paired_market["log_loss"] is not None
                else None
            ),
            "model_brier": total_paired_model["brier"],
            "market_brier": total_paired_market["brier"],
            "brier_delta_model_minus_market": (
                float(total_paired_model["brier"]) - float(total_paired_market["brier"])
                if total_paired_model["brier"] is not None and total_paired_market["brier"] is not None
                else None
            ),
        },
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a leakage-safe football-only walk-forward EPL probability baseline.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--c", type=float, default=1.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_baseline(
        args.database,
        min_train_seasons=args.min_train_seasons,
        c=args.c,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote football-only walk-forward report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
