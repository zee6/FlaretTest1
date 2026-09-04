from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from football1.features import FeatureRow, build_feature_rows
from football1.market_baseline import devig_decimal_odds
from football1.model_baseline import _mean_metrics, _top_label_ece
from football1.offset_slant import _market_probs, fit_offset_slant


LABELS = ("home", "draw", "away")
CLOSING_KEYS = ("B365CH", "B365CD", "B365CA")
DEFAULT_ALPHA = 0.10


@dataclass(frozen=True)
class ClosingObservation:
    base: FeatureRow
    closing_odds: tuple[float, float, float]

    @property
    def season_start_year(self) -> int:
        return self.base.season_start_year

    @property
    def result(self) -> str:
        return self.base.result


def _price(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 1.0:
        return None
    return number


def closing_odds_from_raw(raw: dict[str, Any]) -> tuple[float, float, float] | None:
    values = tuple(_price(raw, key) for key in CLOSING_KEYS)
    if any(value is None for value in values):
        return None
    return (float(values[0]), float(values[1]), float(values[2]))


def _closing_odds_by_match(db_path: Path) -> dict[str, tuple[float, float, float]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT match_id, raw_json FROM matches ORDER BY match_date, match_id").fetchall()
    finally:
        conn.close()

    result: dict[str, tuple[float, float, float]] = {}
    for match_id, raw_json in rows:
        raw = json.loads(raw_json)
        closing = closing_odds_from_raw(raw)
        if closing is not None:
            result[str(match_id)] = closing
    return result


def build_closing_observations(db_path: Path) -> list[ClosingObservation]:
    closing_by_match = _closing_odds_by_match(db_path)
    observations: list[ClosingObservation] = []
    for row in build_feature_rows(db_path):
        if row.b365_home is None or row.b365_draw is None or row.b365_away is None:
            continue
        closing = closing_by_match.get(row.match_id)
        if closing is not None:
            observations.append(ClosingObservation(base=row, closing_odds=closing))
    return observations


def _metrics(items: list[tuple[tuple[float, float, float], str]]) -> dict[str, float | int | None]:
    result = _mean_metrics(items)
    result["top_label_ece"] = _top_label_ece(items)
    return result


def _delta(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def movement_record(
    opening: tuple[float, float, float],
    closing: tuple[float, float, float],
    model: tuple[float, float, float],
) -> dict[str, float | bool | str]:
    residual = tuple(model[i] - opening[i] for i in range(3))
    movement = tuple(closing[i] - opening[i] for i in range(3))
    opening_distance = sum(abs(value) for value in residual)
    closing_distance = sum(abs(model[i] - closing[i]) for i in range(3))
    distance_reduction = opening_distance - closing_distance
    directional_dot = sum(residual[i] * movement[i] for i in range(3))
    call_index = max(range(3), key=lambda i: model[i])
    call_alignment = residual[call_index] * movement[call_index]
    return {
        "opening_l1_distance_to_model": opening_distance,
        "closing_l1_distance_to_model": closing_distance,
        "l1_distance_reduction": distance_reduction,
        "closing_market_is_closer_to_model": distance_reduction > 0.0,
        "directional_dot_product": directional_dot,
        "market_movement_aligns_with_model": directional_dot > 0.0,
        "mean_abs_market_probability_move": sum(abs(value) for value in movement) / 3.0,
        "model_call": LABELS[call_index],
        "model_call_opening_residual": residual[call_index],
        "model_call_market_move": movement[call_index],
        "model_call_moved_toward": call_alignment > 0.0,
    }


def walk_forward_historical_closing_line(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = DEFAULT_ALPHA,
) -> dict[str, Any]:
    """Retrospectively observe whether the Bet365 closing market moves toward Football 1.

    Football 1 is fit strictly on earlier seasons and uses the first/pre-closing
    B365 H/D/A prices as its immutable market offset. B365 closing prices are
    observer-only: they are never supplied to training or prediction.
    """
    if alpha <= 0:
        raise ValueError("alpha must be positive")

    all_rows = [
        row
        for row in build_feature_rows(db_path)
        if row.b365_home is not None and row.b365_draw is not None and row.b365_away is not None
    ]
    observations = build_closing_observations(db_path)
    closing_by_match = {obs.base.match_id: obs for obs in observations}
    seasons = sorted({row.season_start_year for row in all_rows})

    all_opening_items: list[tuple[tuple[float, float, float], str]] = []
    all_closing_items: list[tuple[tuple[float, float, float], str]] = []
    all_model_items: list[tuple[tuple[float, float, float], str]] = []
    all_movement: list[dict[str, float | bool | str]] = []
    season_reports: list[dict[str, Any]] = []

    for test_index, test_season in enumerate(seasons):
        if test_index < min_train_seasons:
            continue
        test = [
            closing_by_match[row.match_id]
            for row in all_rows
            if row.season_start_year == test_season and row.match_id in closing_by_match
        ]
        if not test:
            continue

        train_seasons = seasons[:test_index]
        train = [row for row in all_rows if row.season_start_year in train_seasons]
        if not train:
            continue
        model = fit_offset_slant(train, alpha=alpha)

        opening_items: list[tuple[tuple[float, float, float], str]] = []
        closing_items: list[tuple[tuple[float, float, float], str]] = []
        model_items: list[tuple[tuple[float, float, float], str]] = []
        movements: list[dict[str, float | bool | str]] = []

        for obs in test:
            opening = _market_probs(obs.base)
            closing = devig_decimal_odds(obs.closing_odds)[0]
            prediction = model.predict(obs.base)
            opening_items.append((opening, obs.result))
            closing_items.append((closing, obs.result))
            model_items.append((prediction, obs.result))
            movements.append(movement_record(opening, closing, prediction))

        all_opening_items.extend(opening_items)
        all_closing_items.extend(closing_items)
        all_model_items.extend(model_items)
        all_movement.extend(movements)

        opening_metrics = _metrics(opening_items)
        closing_metrics = _metrics(closing_items)
        model_metrics = _metrics(model_items)
        n = len(movements)
        closer = sum(1 for row in movements if bool(row["closing_market_is_closer_to_model"]))
        aligned = sum(1 for row in movements if bool(row["market_movement_aligns_with_model"]))
        call_toward = sum(1 for row in movements if bool(row["model_call_moved_toward"]))

        season_reports.append(
            {
                "test_season_start_year": test_season,
                "train_matches": len(train),
                "test_matches_with_b365_closing_odds": n,
                "opening_market": opening_metrics,
                "closing_market": {
                    **closing_metrics,
                    "log_loss_delta_vs_opening": _delta(closing_metrics["log_loss"], opening_metrics["log_loss"]),
                    "brier_delta_vs_opening": _delta(closing_metrics["brier"], opening_metrics["brier"]),
                },
                "football1_opening_anchor": {
                    **model_metrics,
                    "log_loss_delta_vs_opening": _delta(model_metrics["log_loss"], opening_metrics["log_loss"]),
                    "log_loss_delta_vs_closing": _delta(model_metrics["log_loss"], closing_metrics["log_loss"]),
                    "brier_delta_vs_opening": _delta(model_metrics["brier"], opening_metrics["brier"]),
                    "brier_delta_vs_closing": _delta(model_metrics["brier"], closing_metrics["brier"]),
                },
                "movement": {
                    "fraction_closing_market_closer_to_football1": closer / n,
                    "mean_l1_distance_reduction": sum(float(row["l1_distance_reduction"]) for row in movements) / n,
                    "fraction_direction_aligned_with_football1": aligned / n,
                    "mean_directional_dot_product": sum(float(row["directional_dot_product"]) for row in movements) / n,
                    "fraction_model_call_moved_toward": call_toward / n,
                    "mean_abs_market_probability_move": sum(float(row["mean_abs_market_probability_move"]) for row in movements) / n,
                },
            }
        )

    if not all_opening_items:
        return {
            "observer": "historical_b365_open_to_close_vs_football1_v1",
            "status": "no_b365_closing_odds_available_zero_decision_weight",
            "matches": 0,
            "seasons": [],
        }

    opening = _metrics(all_opening_items)
    closing = _metrics(all_closing_items)
    model = _metrics(all_model_items)
    n = len(all_movement)
    closer = sum(1 for row in all_movement if bool(row["closing_market_is_closer_to_model"]))
    aligned = sum(1 for row in all_movement if bool(row["market_movement_aligns_with_model"]))
    call_toward = sum(1 for row in all_movement if bool(row["model_call_moved_toward"]))

    return {
        "observer": "historical_b365_open_to_close_vs_football1_v1",
        "status": "historical_retrospective_observer_zero_decision_weight",
        "decision_policy": (
            "Closing prices are observer-only and never enter Football 1 training, prediction, "
            "bet thresholds or stake decisions. This retrospective audit cannot promote a live rule."
        ),
        "split_policy": "walk-forward by season; each Football 1 test prediction is fit only on earlier seasons",
        "market_policy": (
            "Same-book comparison: de-vigged B365H/B365D/B365A first/pre-closing snapshot "
            "versus de-vigged B365CH/B365CD/B365CA closing snapshot; only complete triplets are used."
        ),
        "alpha": alpha,
        "matches": n,
        "test_seasons": [row["test_season_start_year"] for row in season_reports],
        "overall": {
            "opening_market": opening,
            "closing_market": {
                **closing,
                "log_loss_delta_vs_opening": _delta(closing["log_loss"], opening["log_loss"]),
                "brier_delta_vs_opening": _delta(closing["brier"], opening["brier"]),
            },
            "football1_opening_anchor": {
                **model,
                "log_loss_delta_vs_opening": _delta(model["log_loss"], opening["log_loss"]),
                "log_loss_delta_vs_closing": _delta(model["log_loss"], closing["log_loss"]),
                "brier_delta_vs_opening": _delta(model["brier"], opening["brier"]),
                "brier_delta_vs_closing": _delta(model["brier"], closing["brier"]),
            },
            "movement": {
                "fraction_closing_market_closer_to_football1": closer / n,
                "mean_l1_distance_reduction": sum(float(row["l1_distance_reduction"]) for row in all_movement) / n,
                "fraction_direction_aligned_with_football1": aligned / n,
                "mean_directional_dot_product": sum(float(row["directional_dot_product"]) for row in all_movement) / n,
                "fraction_model_call_moved_toward": call_toward / n,
                "mean_abs_market_probability_move": sum(float(row["mean_abs_market_probability_move"]) for row in all_movement) / n,
            },
        },
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit historical Bet365 opening-to-closing movement against walk-forward Football 1 probabilities."
    )
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_historical_closing_line(
        args.database,
        min_train_seasons=args.min_train_seasons,
        alpha=args.alpha,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote historical closing-line observer to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
