from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping


OUTCOMES = ("home", "draw", "away")
DECISION_WEIGHT = 0.0


def _triple(raw: Mapping[str, Any], *, name: str, odds: bool = False) -> dict[str, float]:
    values = {label: float(raw[label]) for label in OUTCOMES}
    if any(not math.isfinite(v) for v in values.values()):
        raise ValueError(f"{name} must contain finite values")
    if odds:
        if any(v <= 1.0 for v in values.values()):
            raise ValueError(f"{name} odds must all be > 1")
    else:
        if any(v <= 0.0 or v >= 1.0 for v in values.values()):
            raise ValueError(f"{name} probabilities must lie strictly between 0 and 1")
        if not math.isclose(sum(values.values()), 1.0, abs_tol=1e-6):
            raise ValueError(f"{name} probabilities must sum to 1")
    return values


def synthetic_dutch_odds(first_odds: float, second_odds: float) -> float:
    """Decimal odds for a two-outcome cover created by dutching separate bets.

    Stakes are split so either winning leg returns the same gross payout.
    """
    first = float(first_odds)
    second = float(second_odds)
    if not math.isfinite(first) or not math.isfinite(second) or first <= 1.0 or second <= 1.0:
        raise ValueError("Dutch legs must have finite decimal odds > 1")
    return 1.0 / ((1.0 / first) + (1.0 / second))


def price_opportunity_analysis(
    *,
    model_probability: Mapping[str, Any],
    market_probability: Mapping[str, Any],
    best_decimal_odds: Mapping[str, Any],
) -> dict[str, Any]:
    """Separate the result call from price ranking across all H/D/A outcomes.

    Positive model EV is reported only as raw research interest. No threshold
    has earned promotion and this function never emits a staking instruction.
    """
    model = _triple(model_probability, name="model")
    market = _triple(market_probability, name="market")
    odds = _triple(best_decimal_odds, name="best_decimal_odds", odds=True)

    outcomes: dict[str, dict[str, Any]] = {}
    for label in OUTCOMES:
        probability = model[label]
        quoted_odds = odds[label]
        outcomes[label] = {
            "model_probability": probability,
            "market_probability": market[label],
            "probability_edge_vs_market": probability - market[label],
            "fair_odds": 1.0 / probability,
            "quoted_odds": quoted_odds,
            "quoted_break_even_probability": 1.0 / quoted_odds,
            "model_ev_at_quoted_odds": probability * quoted_odds - 1.0,
        }

    result_call = max(OUTCOMES, key=lambda label: model[label])
    best_price = max(OUTCOMES, key=lambda label: outcomes[label]["model_ev_at_quoted_odds"])
    positive_price_outcomes = [
        label for label in OUTCOMES if outcomes[label]["model_ev_at_quoted_odds"] > 0.0
    ]

    result_call_ev = outcomes[result_call]["model_ev_at_quoted_odds"]
    return {
        "status": "research_observer_zero_weight",
        "decision_weight": DECISION_WEIGHT,
        "betting_threshold": None,
        "stake_rule": None,
        "result_call": result_call,
        "result_call_probability": model[result_call],
        "best_price_outcome": best_price,
        "best_price_model_ev": outcomes[best_price]["model_ev_at_quoted_odds"],
        "result_plus_price_raw_interest": result_call_ev > 0.0,
        "result_plus_price_model_ev": result_call_ev,
        "positive_price_outcomes": positive_price_outcomes,
        "outcomes": outcomes,
        "warning": (
            "Positive model EV is descriptive research output only. No minimum discrepancy "
            "has been prospectively validated for recommendation or staking."
        ),
    }


def non_loss_analysis(
    *,
    model_probability: Mapping[str, Any],
    market_probability: Mapping[str, Any],
    best_decimal_odds: Mapping[str, Any],
) -> dict[str, Any]:
    """Analyze 1X and X2 as binary events, including synthetic dutched prices."""
    model = _triple(model_probability, name="model")
    market = _triple(market_probability, name="market")
    odds = _triple(best_decimal_odds, name="best_decimal_odds", odds=True)

    def cover(name: str, first: str, second: str) -> dict[str, Any]:
        p_model = model[first] + model[second]
        p_market = market[first] + market[second]
        synthetic = synthetic_dutch_odds(odds[first], odds[second])
        return {
            "id": name,
            "covered_outcomes": [first, second],
            "model_probability": p_model,
            "market_probability": p_market,
            "probability_edge_vs_market": p_model - p_market,
            "fair_odds": 1.0 / p_model,
            "synthetic_dutched_odds": synthetic,
            "synthetic_break_even_probability": 1.0 / synthetic,
            "model_ev_at_synthetic_odds": p_model * synthetic - 1.0,
        }

    home_or_draw = cover("1X", "home", "draw")
    away_or_draw = cover("X2", "draw", "away")
    market_outsider = "home" if market["home"] < market["away"] else "away"
    outsider_cover = home_or_draw if market_outsider == "home" else away_or_draw
    best_cover = max(
        (home_or_draw, away_or_draw),
        key=lambda item: float(item["model_ev_at_synthetic_odds"]),
    )

    return {
        "status": "research_observer_zero_weight",
        "decision_weight": DECISION_WEIGHT,
        "betting_threshold": None,
        "stake_rule": None,
        "home_or_draw": home_or_draw,
        "away_or_draw": away_or_draw,
        "market_outsider_side": market_outsider,
        "outsider_non_loss": outsider_cover,
        "best_non_loss_price": best_cover,
        "warning": (
            "Synthetic dutched odds use the separately available H/D/A prices and therefore "
            "include the cost of buying two outcomes. They are not assumed equal to a bookmaker's "
            "quoted double-chance market."
        ),
    }


def analyze_locked_prediction(record: Mapping[str, Any]) -> dict[str, Any]:
    """Build UI-ready research observations without mutating the immutable ledger record."""
    if record.get("status") != "prediction_locked":
        raise ValueError("Expected an immutable prediction_locked record")
    market_anchor = record.get("market_anchor")
    model = record.get("model")
    if not isinstance(market_anchor, Mapping) or not isinstance(model, Mapping):
        raise ValueError("Prediction record is missing market_anchor or model")

    price = price_opportunity_analysis(
        model_probability=model["probability"],
        market_probability=market_anchor["probability"],
        best_decimal_odds=market_anchor["best_decimal_odds"],
    )
    non_loss = non_loss_analysis(
        model_probability=model["probability"],
        market_probability=market_anchor["probability"],
        best_decimal_odds=market_anchor["best_decimal_odds"],
    )
    features = record.get("features") if isinstance(record.get("features"), Mapping) else {}
    elo_diff = features.get("elo_diff")
    return {
        "schema_version": 1,
        "source_record_id": record.get("record_id"),
        "event_id": record.get("event_id"),
        "status": "research_observer_zero_weight",
        "decision_weight": DECISION_WEIGHT,
        "price": price,
        "non_loss": non_loss,
        "draw_shape_inputs": {
            "model_draw_probability": float(model["probability"]["draw"]),
            "market_draw_probability": float(market_anchor["probability"]["draw"]),
            "draw_probability_edge_vs_market": (
                float(model["probability"]["draw"])
                - float(market_anchor["probability"]["draw"])
            ),
            "absolute_model_home_away_gap": abs(
                float(model["probability"]["home"])
                - float(model["probability"]["away"])
            ),
            "absolute_market_home_away_gap": abs(
                float(market_anchor["probability"]["home"])
                - float(market_anchor["probability"]["away"])
            ),
            "absolute_elo_difference": abs(float(elo_diff)) if elo_diff is not None else None,
        },
        "interface_status": "data_contract_ready_interface_deferred",
    }


def analyze_ledger(ledger_path: Path) -> list[dict[str, Any]]:
    """Read immutable locks and emit derived observations without rewriting them."""
    observations: list[dict[str, Any]] = []
    for line_number, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on ledger line {line_number}") from exc
        if record.get("status") != "prediction_locked":
            continue
        observations.append(analyze_locked_prediction(record))
    return observations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build zero-weight opportunity observations from the prospective ledger.")
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/opportunity_observer.json"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    observations = analyze_ledger(args.ledger)
    payload = {
        "schema_version": 1,
        "status": "research_observer_zero_weight",
        "decision_weight": DECISION_WEIGHT,
        "interface_status": "data_contract_ready_interface_deferred",
        "records": observations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(observations), "decision_weight": DECISION_WEIGHT}, sort_keys=True))


if __name__ == "__main__":
    main()
