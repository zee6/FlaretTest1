from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from football1.features import FeatureRow, build_feature_rows
from football1.model_baseline import _mean_metrics, _top_label_ece
from football1.offset_slant import _market_probs, fit_offset_slant


LABELS = ("H", "D", "A")
REGIME_ORDER = ("very_short", "short", "moderate", "open")
REGIME_DEFINITIONS = {
    "very_short": "favourite decimal odds < 1.50",
    "short": "1.50 <= favourite decimal odds < 1.80",
    "moderate": "1.80 <= favourite decimal odds <= 2.20",
    "open": "favourite decimal odds > 2.20",
}
DEFAULT_ALPHA = 0.10


def favorite_price_regime(favorite_odds: float) -> str:
    """Return the frozen pre-declared favorite-price regime."""
    if favorite_odds <= 1.0:
        raise ValueError("favorite_odds must be greater than 1")
    if favorite_odds < 1.50:
        return "very_short"
    if favorite_odds < 1.80:
        return "short"
    if favorite_odds <= 2.20:
        return "moderate"
    return "open"


def favorite_selection(row: FeatureRow) -> tuple[int, float, str]:
    if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
        raise ValueError(f"Missing Bet365 H/D/A odds for {row.match_id}")
    odds = (float(row.b365_home), float(row.b365_draw), float(row.b365_away))
    index = min(range(3), key=lambda i: odds[i])
    return index, odds[index], LABELS[index]


def _metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    result = _mean_metrics(items)
    result["top_label_ece"] = _top_label_ece(items)
    return result


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def _bucket_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "matches": 0,
            "market": _metrics([]),
            "football1": _metrics([]),
            "favorite": {
                "mean_decimal_odds": None,
                "mean_devig_probability": None,
                "observed_hit_rate": None,
                "calibration_gap_observed_minus_market": None,
                "blind_unit_pnl": 0.0,
                "blind_roi": None,
                "home_favorites": 0,
                "draw_favorites": 0,
                "away_favorites": 0,
            },
        }

    market_items = [(r["market"], r["result"]) for r in records]
    model_items = [(r["football1"], r["result"]) for r in records]
    market_metrics = _metrics(market_items)
    model_metrics = _metrics(model_items)

    hit = 0
    pnl = 0.0
    favorite_probs: list[float] = []
    favorite_odds: list[float] = []
    model_minus_market: list[float] = []
    move_toward_favorite = 0
    favorite_counts = {"H": 0, "D": 0, "A": 0}

    for record in records:
        index = int(record["favorite_index"])
        odds = float(record["favorite_odds"])
        favorite_counts[LABELS[index]] += 1
        favorite_odds.append(odds)
        favorite_probs.append(float(record["market"][index]))
        delta = float(record["football1"][index]) - float(record["market"][index])
        model_minus_market.append(delta)
        if delta > 0.0:
            move_toward_favorite += 1
        if record["result"] == LABELS[index]:
            hit += 1
            pnl += odds - 1.0
        else:
            pnl -= 1.0

    n = len(records)
    mean_market_favorite = sum(favorite_probs) / n
    observed = hit / n

    return {
        "matches": n,
        "market": market_metrics,
        "football1": {
            **model_metrics,
            "log_loss_delta_vs_market": _delta(model_metrics["log_loss"], market_metrics["log_loss"]),
            "brier_delta_vs_market": _delta(model_metrics["brier"], market_metrics["brier"]),
        },
        "favorite": {
            "mean_decimal_odds": sum(favorite_odds) / n,
            "mean_devig_probability": mean_market_favorite,
            "observed_hit_rate": observed,
            "calibration_gap_observed_minus_market": observed - mean_market_favorite,
            "blind_unit_pnl": pnl,
            "blind_roi": pnl / n,
            "home_favorites": favorite_counts["H"],
            "draw_favorites": favorite_counts["D"],
            "away_favorites": favorite_counts["A"],
            "mean_football1_probability_move_on_market_favorite": sum(model_minus_market) / n,
            "fraction_football1_moves_probability_toward_market_favorite": move_toward_favorite / n,
        },
    }


def walk_forward_market_regime_audit(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = DEFAULT_ALPHA,
) -> dict[str, Any]:
    """Audit fixed favorite-price market regimes on chronologically held-out seasons.

    The regime boundaries are frozen before seeing this audit's results. Every
    Football 1 probability for a test season is produced by an offset-slant
    model fit only on earlier seasons. Regime assignment uses only the same
    pre-match Bet365 H/D/A quote used as the historical market starting point.
    """
    rows = [
        row
        for row in build_feature_rows(db_path)
        if row.b365_home is not None and row.b365_draw is not None and row.b365_away is not None
    ]
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    overall_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    season_reports: list[dict[str, Any]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        training_seasons = seasons[:test_index]
        train = [row for row in rows if row.season_start_year in training_seasons]
        test = [row for row in rows if row.season_start_year == test_season]
        if not test:
            continue

        model = fit_offset_slant(train, alpha=alpha)
        season_records: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for row in test:
            market = _market_probs(row)
            football1 = model.predict(row)
            favorite_index, favorite_odds, favorite_label = favorite_selection(row)
            regime = favorite_price_regime(favorite_odds)
            record = {
                "match_id": row.match_id,
                "result": row.result,
                "market": market,
                "football1": football1,
                "favorite_index": favorite_index,
                "favorite_label": favorite_label,
                "favorite_odds": favorite_odds,
            }
            season_records[regime].append(record)
            overall_records[regime].append(record)

        season_reports.append(
            {
                "test_season_start_year": test_season,
                "training_seasons": training_seasons,
                "train_matches": len(train),
                "test_matches": len(test),
                "regimes": {name: _bucket_summary(season_records[name]) for name in REGIME_ORDER},
            }
        )

    all_test_records = [record for name in REGIME_ORDER for record in overall_records[name]]
    all_market_items = [(r["market"], r["result"]) for r in all_test_records]
    all_model_items = [(r["football1"], r["result"]) for r in all_test_records]
    market_metrics = _metrics(all_market_items)
    model_metrics = _metrics(all_model_items)

    return {
        "status": "historical_walk_forward_fixed_market_regime_audit_zero_decision_weight",
        "audit": "favorite_price_regimes_v1",
        "market_source": "Bet365 H/D/A pre-closing snapshot, de-vigged for probability scoring",
        "regime_policy": (
            "Boundaries were fixed before this audit: very_short <1.50; short 1.50-<1.80; "
            "moderate 1.80-2.20 inclusive; open >2.20. Do not move these boundaries after inspecting results."
        ),
        "regime_definitions": REGIME_DEFINITIONS,
        "split_policy": "walk-forward by season; each test season uses Football 1 parameters fit only on earlier seasons",
        "alpha": alpha,
        "matches": len(all_test_records),
        "test_seasons": [report["test_season_start_year"] for report in season_reports],
        "overall": {
            "market": market_metrics,
            "football1": {
                **model_metrics,
                "log_loss_delta_vs_market": _delta(model_metrics["log_loss"], market_metrics["log_loss"]),
                "brier_delta_vs_market": _delta(model_metrics["brier"], market_metrics["brier"]),
            },
            "regimes": {name: _bucket_summary(overall_records[name]) for name in REGIME_ORDER},
        },
        "interpretation_guardrails": [
            "Favorite ROI is a one-unit descriptive audit of the bookmaker favorite in each pre-declared price band, not a betting strategy.",
            "No bucket may be promoted because it looks profitable after this audit; any such hypothesis must be frozen and tested on fresh prospective data.",
            "Football 1 remains zero promotional weight unless it improves genuinely unseen probability forecasts.",
            "The bucket labels describe market geometry, not certainty about an individual match.",
        ],
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit fixed EPL bookmaker favorite-price regimes.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_market_regime_audit(
        args.database,
        min_train_seasons=args.min_train_seasons,
        alpha=args.alpha,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote market regime audit to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
