from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from football1.features import FEATURE_NAMES, FeatureRow, build_feature_rows, feature_vector
from football1.market_baseline import devig_decimal_odds
from football1.model_baseline import _mean_metrics, _top_label_ece


RESULTS = ("H", "D", "A")
MARKET_FEATURE_NAMES = ("market_home", "market_draw", "market_away")
RF_FEATURE_NAMES = FEATURE_NAMES + MARKET_FEATURE_NAMES

# Frozen before the first audit. These are deliberately conservative rather
# than tuned against OOS results.
DEFAULT_N_ESTIMATORS = 400
DEFAULT_MAX_DEPTH = 7
DEFAULT_MIN_SAMPLES_LEAF = 20
DEFAULT_MAX_FEATURES = "sqrt"
DEFAULT_RANDOM_STATE = 17
DEFAULT_RESIDUAL_WEIGHT = 0.10


def _market_probs(row: FeatureRow) -> tuple[float, float, float]:
    if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
        raise ValueError(f"Missing Bet365 odds for {row.match_id}")
    return devig_decimal_odds((row.b365_home, row.b365_draw, row.b365_away))[0]


def random_forest_vector(row: FeatureRow) -> list[float]:
    """Leakage-safe football features plus the de-vigged market starting point."""
    return feature_vector(row) + list(_market_probs(row))


def _probabilities_in_hda(
    model: RandomForestClassifier,
    vector: list[float],
) -> tuple[float, float, float]:
    raw = model.predict_proba([vector])[0]
    mapping = {label: float(raw[i]) for i, label in enumerate(model.classes_)}
    return (mapping["H"], mapping["D"], mapping["A"])


def geometric_market_correction(
    market: tuple[float, float, float],
    candidate: tuple[float, float, float],
    *,
    weight: float = DEFAULT_RESIDUAL_WEIGHT,
) -> tuple[float, float, float]:
    """Move only part-way from market toward the candidate in log-probability space.

    weight=0 reproduces the market exactly. weight=1 reproduces the candidate.
    The first audit freezes weight at 0.10; it is not tuned on held-out results.
    """
    if not 0.0 <= weight <= 1.0:
        raise ValueError("weight must be between 0 and 1")
    m = np.asarray(market, dtype=float)
    c = np.asarray(candidate, dtype=float)
    if m.shape != (3,) or c.shape != (3,):
        raise ValueError("market and candidate must each contain H/D/A probabilities")
    if np.any(~np.isfinite(m)) or np.any(~np.isfinite(c)) or np.any(m <= 0) or np.any(c < 0):
        raise ValueError("probabilities must be finite; market must be positive and candidate non-negative")
    if not math.isclose(float(m.sum()), 1.0, abs_tol=1e-9) or not math.isclose(float(c.sum()), 1.0, abs_tol=1e-9):
        raise ValueError("probabilities must sum to 1")

    eps = 1e-9
    c = np.clip(c, eps, 1.0)
    log_mix = (1.0 - weight) * np.log(m) + weight * np.log(c)
    log_mix -= np.max(log_mix)
    mixed = np.exp(log_mix)
    mixed /= mixed.sum()
    return (float(mixed[0]), float(mixed[1]), float(mixed[2]))


def _fit_model(rows: list[FeatureRow]) -> RandomForestClassifier:
    y = [row.result for row in rows]
    if set(y) != set(RESULTS):
        raise ValueError("Training block lacks all H/D/A classes")
    model = RandomForestClassifier(
        n_estimators=DEFAULT_N_ESTIMATORS,
        max_depth=DEFAULT_MAX_DEPTH,
        min_samples_leaf=DEFAULT_MIN_SAMPLES_LEAF,
        max_features=DEFAULT_MAX_FEATURES,
        random_state=DEFAULT_RANDOM_STATE,
        n_jobs=-1,
        class_weight=None,
    )
    model.fit([random_forest_vector(row) for row in rows], y)
    return model


def _metric_block(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    result = _mean_metrics(items)
    result["top_label_ece"] = _top_label_ece(items)
    return result


def _economic_metrics(
    predictions: list[tuple[tuple[float, float, float], FeatureRow]],
) -> dict[str, object]:
    top_pick_bets = 0
    top_pick_wins = 0
    top_pick_pnl = 0.0
    positive_ev_bets = 0
    positive_ev_wins = 0
    positive_ev_pnl = 0.0

    for probs, row in predictions:
        if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
            continue
        odds = (row.b365_home, row.b365_draw, row.b365_away)
        actual_index = RESULTS.index(row.result)

        top_index = max(range(3), key=lambda i: probs[i])
        top_pick_bets += 1
        if top_index == actual_index:
            top_pick_wins += 1
            top_pick_pnl += odds[top_index] - 1.0
        else:
            top_pick_pnl -= 1.0

        evs = tuple(probs[i] * odds[i] - 1.0 for i in range(3))
        best_index = max(range(3), key=lambda i: evs[i])
        if evs[best_index] > 0.0:
            positive_ev_bets += 1
            if best_index == actual_index:
                positive_ev_wins += 1
                positive_ev_pnl += odds[best_index] - 1.0
            else:
                positive_ev_pnl -= 1.0

    return {
        "blind_top_pick": {
            "bets": top_pick_bets,
            "wins": top_pick_wins,
            "pnl_units": top_pick_pnl,
            "roi": top_pick_pnl / top_pick_bets if top_pick_bets else None,
        },
        "positive_model_ev_no_threshold": {
            "rule": "one unit on the single H/D/A outcome with highest model EV only when that EV is > 0; no edge-size threshold",
            "bets": positive_ev_bets,
            "wins": positive_ev_wins,
            "pnl_units": positive_ev_pnl,
            "roi": positive_ev_pnl / positive_ev_bets if positive_ev_bets else None,
        },
    }


def _movement_summary(
    market_items: list[tuple[tuple[float, float, float], str]],
    corrected_items: list[tuple[tuple[float, float, float], str]],
) -> dict[str, float | int | None]:
    if not market_items:
        return {"matches": 0, "mean_abs_probability_move": None, "max_abs_probability_move": None}
    moves: list[float] = []
    for (market, _), (corrected, _) in zip(market_items, corrected_items, strict=True):
        moves.extend(abs(corrected[i] - market[i]) for i in range(3))
    return {
        "matches": len(market_items),
        "mean_abs_probability_move": sum(moves) / len(moves),
        "max_abs_probability_move": max(moves),
    }


def walk_forward_random_forest_residual(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    residual_weight: float = DEFAULT_RESIDUAL_WEIGHT,
) -> dict[str, object]:
    """Audit a Random Forest as a market-anchored correction candidate.

    Each test season is predicted by a model fit only on earlier seasons. The
    pre-match features themselves are date-frozen by ``build_feature_rows``.
    Only rows with complete B365 H/D/A prices are used because the market is an
    explicit input and starting point.
    """
    rows = [
        row
        for row in build_feature_rows(db_path)
        if row.b365_home is not None and row.b365_draw is not None and row.b365_away is not None
    ]
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    all_market: list[tuple[tuple[float, float, float], str]] = []
    all_rf: list[tuple[tuple[float, float, float], str]] = []
    all_corrected: list[tuple[tuple[float, float, float], str]] = []
    all_market_econ: list[tuple[tuple[float, float, float], FeatureRow]] = []
    all_rf_econ: list[tuple[tuple[float, float, float], FeatureRow]] = []
    all_corrected_econ: list[tuple[tuple[float, float, float], FeatureRow]] = []
    season_reports: list[dict[str, object]] = []
    latest_importance: dict[str, float] | None = None

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        training_seasons = seasons[:test_index]
        train = [row for row in rows if row.season_start_year in training_seasons]
        test = [row for row in rows if row.season_start_year == test_season]
        model = _fit_model(train)

        market_items: list[tuple[tuple[float, float, float], str]] = []
        rf_items: list[tuple[tuple[float, float, float], str]] = []
        corrected_items: list[tuple[tuple[float, float, float], str]] = []
        market_econ: list[tuple[tuple[float, float, float], FeatureRow]] = []
        rf_econ: list[tuple[tuple[float, float, float], FeatureRow]] = []
        corrected_econ: list[tuple[tuple[float, float, float], FeatureRow]] = []

        for row in test:
            market = _market_probs(row)
            rf = _probabilities_in_hda(model, random_forest_vector(row))
            corrected = geometric_market_correction(market, rf, weight=residual_weight)

            market_items.append((market, row.result))
            rf_items.append((rf, row.result))
            corrected_items.append((corrected, row.result))
            market_econ.append((market, row))
            rf_econ.append((rf, row))
            corrected_econ.append((corrected, row))

        all_market.extend(market_items)
        all_rf.extend(rf_items)
        all_corrected.extend(corrected_items)
        all_market_econ.extend(market_econ)
        all_rf_econ.extend(rf_econ)
        all_corrected_econ.extend(corrected_econ)

        market_metrics = _metric_block(market_items)
        rf_metrics = _metric_block(rf_items)
        corrected_metrics = _metric_block(corrected_items)
        season_reports.append(
            {
                "test_season_start_year": test_season,
                "training_seasons": training_seasons,
                "train_matches": len(train),
                "test_matches": len(test),
                "raw_market": market_metrics,
                "random_forest_standalone": rf_metrics,
                "market_plus_fixed_rf_residual": {
                    **corrected_metrics,
                    "log_loss_delta_vs_market": (
                        float(corrected_metrics["log_loss"]) - float(market_metrics["log_loss"])
                        if corrected_metrics["log_loss"] is not None and market_metrics["log_loss"] is not None
                        else None
                    ),
                    "brier_delta_vs_market": (
                        float(corrected_metrics["brier"]) - float(market_metrics["brier"])
                        if corrected_metrics["brier"] is not None and market_metrics["brier"] is not None
                        else None
                    ),
                    "probability_movement": _movement_summary(market_items, corrected_items),
                },
                "economics": {
                    "market": _economic_metrics(market_econ),
                    "random_forest": _economic_metrics(rf_econ),
                    "corrected": _economic_metrics(corrected_econ),
                },
            }
        )

        if test_index == len(seasons) - 1:
            latest_importance = {
                name: float(value)
                for name, value in sorted(
                    zip(RF_FEATURE_NAMES, model.feature_importances_, strict=True),
                    key=lambda item: item[1],
                    reverse=True,
                )
            }

    market_metrics = _metric_block(all_market)
    rf_metrics = _metric_block(all_rf)
    corrected_metrics = _metric_block(all_corrected)

    return {
        "status": "historical_walk_forward_audit_only_zero_live_weight",
        "model": "market_aware_random_forest_residual_v1",
        "market_source": "B365 pre-closing, de-vigged",
        "feature_names": list(RF_FEATURE_NAMES),
        "split_policy": "walk-forward by season; each test season uses model parameters fit only on earlier seasons",
        "same_day_policy": "all football features on a date are snapshotted before any result from that date updates team state",
        "hyperparameter_policy": (
            "n_estimators=400, max_depth=7, min_samples_leaf=20, max_features=sqrt, random_state=17, "
            "residual_weight=0.10 frozen before first OOS audit; no OOS tuning"
        ),
        "residual_definition": (
            "geometric/log-probability interpolation from de-vigged market toward the market-aware Random Forest; "
            "weight 0 reproduces market, weight 1 reproduces Random Forest"
        ),
        "overall": {
            "raw_market": market_metrics,
            "random_forest_standalone": rf_metrics,
            "market_plus_fixed_rf_residual": {
                **corrected_metrics,
                "log_loss_delta_vs_market": (
                    float(corrected_metrics["log_loss"]) - float(market_metrics["log_loss"])
                    if corrected_metrics["log_loss"] is not None and market_metrics["log_loss"] is not None
                    else None
                ),
                "brier_delta_vs_market": (
                    float(corrected_metrics["brier"]) - float(market_metrics["brier"])
                    if corrected_metrics["brier"] is not None and market_metrics["brier"] is not None
                    else None
                ),
                "probability_movement": _movement_summary(all_market, all_corrected),
            },
        },
        "economics": {
            "market": _economic_metrics(all_market_econ),
            "random_forest": _economic_metrics(all_rf_econ),
            "corrected": _economic_metrics(all_corrected_econ),
        },
        "latest_training_impurity_importance": {
            "warning": "descriptive training-set Random Forest impurity importance only; not OOS proof that a feature adds value",
            "values": latest_importance,
        },
        "promotion_rule": (
            "No promotion from this audit alone. Any apparent advantage must survive pre-specified fresh/prospective testing; "
            "no subgroup or threshold may be selected after inspecting these OOS results."
        ),
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the market-anchored Random Forest residual EPL audit.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--residual-weight", type=float, default=DEFAULT_RESIDUAL_WEIGHT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_random_forest_residual(
        args.database,
        min_train_seasons=args.min_train_seasons,
        residual_weight=args.residual_weight,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote Random Forest residual audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
