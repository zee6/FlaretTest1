from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from typing import Iterable

from football1.elo import (
    CLASS_ORDER,
    _fit_probability_layer,
    _predict_probs,
    build_elo_history,
)


CONFIDENCE_BANDS = (
    ("under_40pct", 0.0, 0.40),
    ("40_to_50pct", 0.40, 0.50),
    ("50_to_60pct", 0.50, 0.60),
    ("60_to_70pct", 0.60, 0.70),
    ("70_to_80pct", 0.70, 0.80),
    ("80pct_plus", 0.80, math.inf),
)

ODDS_BANDS = (
    ("under_1_50", 1.0, 1.50),
    ("1_50_to_2_00", 1.50, 2.00),
    ("2_00_to_3_00", 2.00, 3.00),
    ("3_00_to_5_00", 3.00, 5.00),
    ("5_00_plus", 5.00, math.inf),
)


def _parse_b365_odds(raw_json: str) -> tuple[float, float, float] | None:
    raw = json.loads(raw_json)
    try:
        odds = tuple(float(str(raw.get(name, "")).strip()) for name in ("B365H", "B365D", "B365A"))
    except (TypeError, ValueError):
        return None
    if any((not math.isfinite(x)) or x <= 1.0 for x in odds):
        return None
    return odds  # type: ignore[return-value]


def _load_b365_odds(db_path: Path) -> dict[str, tuple[float, float, float]]:
    conn = sqlite3.connect(db_path)
    try:
        records = conn.execute("SELECT match_id, raw_json FROM matches").fetchall()
    finally:
        conn.close()

    out: dict[str, tuple[float, float, float]] = {}
    for match_id, raw_json in records:
        odds = _parse_b365_odds(str(raw_json))
        if odds is not None:
            out[str(match_id)] = odds
    return out


def _band_name(value: float, bands: tuple[tuple[str, float, float], ...]) -> str:
    for name, lo, hi in bands:
        if lo <= value < hi:
            return name
    raise ValueError(f"No band configured for value {value}")


def _summarize(picks: Iterable[dict[str, object]]) -> dict[str, object]:
    items = list(picks)
    correct = sum(bool(x["correct"]) for x in items)
    prices = [x for x in items if x.get("b365_decimal_odds") is not None]
    pnl = sum(float(x["flat_stake_profit_units"]) for x in prices)
    n = len(items)
    price_n = len(prices)
    return {
        "picks": n,
        "correct": correct,
        "incorrect": n - correct,
        "hit_rate": correct / n if n else None,
        "mean_top_probability": (
            sum(float(x["elo_top_probability"]) for x in items) / n if n else None
        ),
        "blind_flat_stake_b365": {
            "bets": price_n,
            "profit_units": pnl,
            "roi": pnl / price_n if price_n else None,
            "mean_decimal_odds": (
                sum(float(x["b365_decimal_odds"]) for x in prices) / price_n
                if price_n
                else None
            ),
        },
    }


def _group_summary(
    picks: list[dict[str, object]],
    key_fn,
    ordered_keys: Iterable[str],
) -> dict[str, dict[str, object]]:
    return {
        key: _summarize([x for x in picks if key_fn(x) == key])
        for key in ordered_keys
    }


def build_elo_observer_report(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
) -> dict[str, object]:
    """Build observer-friendly diagnostics for the frozen walk-forward Elo model.

    This report does not tune or alter Elo. It simply asks intuitive questions:
    how often was the top 1X2 pick right, what happened at different confidence
    and bookmaker-price levels, and did Elo agree with the market favourite?
    """
    rows, _ = build_elo_history(db_path)
    b365_odds = _load_b365_odds(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    picks: list[dict[str, object]] = []
    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train = [row for row in rows if row.season_start_year in seasons[:test_index]]
        test = [row for row in rows if row.season_start_year == test_season]
        model = _fit_probability_layer(train)

        for row in test:
            probs = _predict_probs(model, row)
            idx = max(range(3), key=lambda k: probs[k])
            predicted = CLASS_ORDER[idx]
            top_prob = float(probs[idx])
            correct = predicted == row.result

            odds_triplet = b365_odds.get(row.match_id)
            picked_odds = float(odds_triplet[idx]) if odds_triplet is not None else None
            profit = (
                picked_odds - 1.0 if correct else -1.0
                if picked_odds is not None
                else None
            )
            # The conditional expression above is intentionally expanded below
            # to avoid ambiguity when no bookmaker price exists.
            if picked_odds is None:
                profit = None
            elif correct:
                profit = picked_odds - 1.0
            else:
                profit = -1.0

            market_top = None
            market_prob_for_pick = None
            if row.market_probs is not None:
                market_idx = max(range(3), key=lambda k: row.market_probs[k])
                market_top = CLASS_ORDER[market_idx]
                market_prob_for_pick = float(row.market_probs[idx])

            picks.append(
                {
                    "match_id": row.match_id,
                    "season_start_year": row.season_start_year,
                    "date": row.match_date,
                    "home_team": row.home_team,
                    "away_team": row.away_team,
                    "actual_result": row.result,
                    "elo_probabilities": {
                        "H": float(probs[0]),
                        "D": float(probs[1]),
                        "A": float(probs[2]),
                    },
                    "elo_top_pick": predicted,
                    "elo_top_probability": top_prob,
                    "correct": correct,
                    "confidence_band": _band_name(top_prob, CONFIDENCE_BANDS),
                    "b365_decimal_odds": picked_odds,
                    "b365_odds_band": (
                        _band_name(picked_odds, ODDS_BANDS)
                        if picked_odds is not None
                        else None
                    ),
                    "market_top_pick": market_top,
                    "elo_market_agreement": (
                        predicted == market_top if market_top is not None else None
                    ),
                    "market_fair_probability_for_elo_pick": market_prob_for_pick,
                    "elo_minus_market_probability": (
                        top_prob - market_prob_for_pick
                        if market_prob_for_pick is not None
                        else None
                    ),
                    "elo_price_ev": (
                        top_prob * picked_odds - 1.0
                        if picked_odds is not None
                        else None
                    ),
                    "flat_stake_profit_units": profit,
                }
            )

    by_outcome = _group_summary(picks, lambda x: str(x["elo_top_pick"]), CLASS_ORDER)
    by_confidence = _group_summary(
        picks,
        lambda x: str(x["confidence_band"]),
        [x[0] for x in CONFIDENCE_BANDS],
    )
    priced = [x for x in picks if x["b365_odds_band"] is not None]
    by_odds = _group_summary(
        priced,
        lambda x: str(x["b365_odds_band"]),
        [x[0] for x in ODDS_BANDS],
    )
    agreement = {
        "agree_with_market_top_pick": _summarize(
            [x for x in picks if x["elo_market_agreement"] is True]
        ),
        "disagree_with_market_top_pick": _summarize(
            [x for x in picks if x["elo_market_agreement"] is False]
        ),
    }

    latest = sorted(picks, key=lambda x: (str(x["date"]), str(x["match_id"])), reverse=True)[:20]

    return {
        "report": "elo_observer_v1",
        "model": "elo_1x2_v1",
        "status": "observer diagnostic only; does not alter model probabilities or select bets",
        "split_policy": "same frozen walk-forward Elo evaluation: first 3 seasons warm-up, later seasons OOS",
        "interpretation": {
            "hit_rate": "share of matches where Elo's highest-probability H/D/A label matched the final result",
            "blind_flat_stake_b365": "one unit on every Elo top pick at Bet365 pre-closing decimal odds; no filtering or threshold selection",
            "elo_price_ev": "Elo top-pick probability multiplied by available decimal price minus one; descriptive only",
        },
        "overall": _summarize(picks),
        "by_predicted_outcome": by_outcome,
        "by_elo_confidence": by_confidence,
        "by_b365_odds_for_elo_pick": by_odds,
        "market_agreement": agreement,
        "latest_predictions": latest,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Observer-friendly walk-forward EPL Elo diagnostics.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_elo_observer_report(args.database, min_train_seasons=args.min_train_seasons)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote Elo observer report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
