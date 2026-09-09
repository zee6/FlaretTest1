from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping


SUPPORTED_MARKETS = frozenset({"h2h"})
OUTCOMES = ("home", "draw", "away")
PRICE_WITHIN_1 = 0.01
PRICE_WITHIN_2 = 0.02


def _finite(value: Any, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _decimal_odds(value: Any, *, name: str) -> float:
    result = _finite(value, name=name)
    if result <= 1.0:
        raise ValueError(f"{name} must be > 1.0")
    return result


def _probability_triple(raw: Mapping[str, Any], *, name: str) -> dict[str, float]:
    values = {outcome: _finite(raw[outcome], name=f"{name}.{outcome}") for outcome in OUTCOMES}
    if any(value <= 0.0 or value >= 1.0 for value in values.values()):
        raise ValueError(f"{name} probabilities must lie strictly between 0 and 1")
    if not math.isclose(sum(values.values()), 1.0, abs_tol=1e-6):
        raise ValueError(f"{name} probabilities must sum to 1")
    return values


def _best_price_for_outcome(reference: Mapping[str, Any], outcome: str) -> dict[str, Any] | None:
    raw = reference.get("best_observed_price")
    if not isinstance(raw, Mapping):
        return None
    candidate = raw.get(outcome)
    if candidate is None:
        return None
    if isinstance(candidate, Mapping):
        odds = _decimal_odds(candidate.get("odds"), name=f"best_observed_price.{outcome}.odds")
        return {
            "odds": odds,
            "bookmaker_key": candidate.get("bookmaker_key"),
            "bookmaker_title": candidate.get("bookmaker_title"),
            "observed_at_utc": candidate.get("observed_at_utc"),
            "books_checked": candidate.get("books_checked"),
        }
    return {
        "odds": _decimal_odds(candidate, name=f"best_observed_price.{outcome}"),
        "bookmaker_key": None,
        "bookmaker_title": None,
        "observed_at_utc": None,
        "books_checked": None,
    }


def classify_price(user_odds: float, best_odds: float | None) -> dict[str, Any]:
    """Classify only price quality; never football confidence or bet quality."""
    if best_odds is None:
        return {
            "status": "best_price_unknown",
            "shortfall_fraction": None,
            "best_vs_user_gross_return_uplift": None,
        }
    user = _decimal_odds(user_odds, name="user_odds")
    best = _decimal_odds(best_odds, name="best_odds")
    if user > best and not math.isclose(user, best, abs_tol=1e-12):
        return {
            "status": "better_than_observed_best",
            "shortfall_fraction": 0.0,
            "best_vs_user_gross_return_uplift": best / user - 1.0,
        }
    shortfall = max(0.0, 1.0 - user / best)
    if math.isclose(shortfall, 0.0, abs_tol=1e-12):
        status = "best_observed"
    elif shortfall <= PRICE_WITHIN_1 + 1e-12:
        status = "near_best_within_1pct"
    elif shortfall <= PRICE_WITHIN_2 + 1e-12:
        status = "near_best_within_2pct"
    else:
        status = "materially_below_best"
    return {
        "status": status,
        "shortfall_fraction": shortfall,
        "best_vs_user_gross_return_uplift": best / user - 1.0,
    }


def _price_explanation(status: str) -> str:
    return {
        "best_price_unknown": "No synchronized best-price observation is available for this leg.",
        "better_than_observed_best": "Your quoted price is better than Football 1's observed best price.",
        "best_observed": "Your quoted price matches the best observed sportsbook price.",
        "near_best_within_1pct": "Your quoted price is within 1% of the best observed sportsbook price.",
        "near_best_within_2pct": "Your quoted price is within 2% of the best observed sportsbook price.",
        "materially_below_best": "Your quoted price is more than 2% below the best observed sportsbook price.",
    }[status]


def evaluate_leg(leg: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, Any]:
    market = str(leg.get("market") or "")
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market for Bet Check v1: {market!r}")
    outcome = str(leg.get("outcome") or "")
    if outcome not in OUTCOMES:
        raise ValueError(f"Unsupported h2h outcome: {outcome!r}")
    event_id = str(leg.get("event_id") or "")
    if not event_id:
        raise ValueError("leg.event_id is required")
    if str(reference.get("event_id") or "") != event_id:
        raise ValueError(f"Reference event_id does not match leg event_id: {event_id}")

    user_odds = _decimal_odds(leg.get("quoted_odds"), name="leg.quoted_odds")
    market_probability = _probability_triple(
        reference.get("market_probability") or {}, name="reference.market_probability"
    )
    model_probability = _probability_triple(
        reference.get("football1_probability") or {}, name="reference.football1_probability"
    )
    p_market = market_probability[outcome]
    p_model = model_probability[outcome]
    best = _best_price_for_outcome(reference, outcome)
    price_quality = classify_price(user_odds, float(best["odds"]) if best else None)

    result_call = max(OUTCOMES, key=lambda key: model_probability[key])
    model_edge = p_model - p_market
    break_even = 1.0 / user_odds
    market_arithmetic_ev = p_market * user_odds - 1.0
    model_arithmetic_ev = p_model * user_odds - 1.0

    return {
        "event_id": event_id,
        "market": market,
        "outcome": outcome,
        "home_team": reference.get("home_team"),
        "away_team": reference.get("away_team"),
        "user_quote": {
            "decimal_odds": user_odds,
            "break_even_probability": break_even,
            "bookmaker": leg.get("bookmaker"),
        },
        "market": {
            "probability": p_market,
            "fair_odds": 1.0 / p_market,
            "arithmetic_ev_at_user_quote": market_arithmetic_ev,
        },
        "football1": {
            "probability": p_model,
            "fair_odds": 1.0 / p_model,
            "probability_edge_vs_market": model_edge,
            "arithmetic_ev_at_user_quote": model_arithmetic_ev,
            "result_call": result_call,
            "is_result_call": outcome == result_call,
        },
        "best_price": best,
        "price_quality": {
            **price_quality,
            "explanation": _price_explanation(str(price_quality["status"])),
        },
        "weakness_metrics": {
            "conservative_market_arithmetic_ev": market_arithmetic_ev,
            "price_shortfall_fraction": price_quality["shortfall_fraction"],
        },
        "governance": {
            "price_changes_probability": False,
            "raw_positive_ev_is_recommendation": False,
            "football1_residual_is_confidence": False,
        },
    }


def _reference_map(references: Mapping[str, Any] | list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    if isinstance(references, Mapping):
        if "events" in references and isinstance(references["events"], list):
            source = references["events"]
        else:
            source = list(references.values())
    else:
        source = references
    result: dict[str, Mapping[str, Any]] = {}
    for reference in source:
        event_id = str(reference.get("event_id") or "")
        if not event_id:
            raise ValueError("Every reference event requires event_id")
        if event_id in result:
            raise ValueError(f"Duplicate reference event_id: {event_id}")
        result[event_id] = reference
    return result


def _weakest_leg(legs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not legs:
        return None
    # The market benchmark is deliberately primary because Football 1 residual
    # magnitude has not earned confidence status. Price shortfall breaks ties.
    def key(item: tuple[int, dict[str, Any]]) -> tuple[float, float, int]:
        index, leg = item
        market_ev = float(leg["weakness_metrics"]["conservative_market_arithmetic_ev"])
        shortfall_raw = leg["weakness_metrics"]["price_shortfall_fraction"]
        shortfall = float(shortfall_raw) if shortfall_raw is not None else 0.0
        return (market_ev, -shortfall, index)

    index, leg = min(enumerate(legs), key=key)
    return {
        "leg_index": index,
        "event_id": leg["event_id"],
        "outcome": leg["outcome"],
        "basis": "lowest de-vigged market arithmetic EV at the user's quoted price; price shortfall breaks ties",
        "market_arithmetic_ev": leg["weakness_metrics"]["conservative_market_arithmetic_ev"],
        "price_quality": leg["price_quality"]["status"],
    }


def _combined_analysis(
    legs: list[dict[str, Any]],
    *,
    user_combined_odds: float,
    leg_price_product: float,
) -> dict[str, Any]:
    duplicate_event = len({str(leg["event_id"]) for leg in legs}) != len(legs)
    base = {
        "user_combined_odds": user_combined_odds,
        "product_of_user_leg_odds": leg_price_product,
        "combined_odds_vs_leg_product": user_combined_odds / leg_price_product - 1.0,
        "potential_gross_return_per_unit_staked": user_combined_odds,
    }
    if duplicate_event:
        return {
            **base,
            "joint_probability_status": "unsupported_correlated_same_event",
            "market_independence_probability": None,
            "football1_independence_probability": None,
            "market_independence_fair_odds": None,
            "football1_independence_fair_odds": None,
            "market_independence_ev_at_user_combined_odds": None,
            "football1_independence_ev_at_user_combined_odds": None,
            "warning": (
                "Bet Check v1 will not multiply probabilities for multiple legs from the same event. "
                "A joint/correlated market model is required."
            ),
        }

    market_joint = math.prod(float(leg["market"]["probability"]) for leg in legs)
    model_joint = math.prod(float(leg["football1"]["probability"]) for leg in legs)
    return {
        **base,
        "joint_probability_status": "independence_only_distinct_events",
        "market_independence_probability": market_joint,
        "football1_independence_probability": model_joint,
        "market_independence_fair_odds": 1.0 / market_joint,
        "football1_independence_fair_odds": 1.0 / model_joint,
        "market_independence_ev_at_user_combined_odds": market_joint * user_combined_odds - 1.0,
        "football1_independence_ev_at_user_combined_odds": model_joint * user_combined_odds - 1.0,
        "warning": (
            "Combined probabilities multiply distinct-event legs only as an independence approximation. "
            "They are not a validated joint-probability model and are not a betting recommendation."
        ),
    }


def evaluate_bet(bet: Mapping[str, Any], references: Mapping[str, Any] | list[Mapping[str, Any]]) -> dict[str, Any]:
    currency = str(bet.get("currency") or "GBP").upper()
    if currency != "GBP":
        raise ValueError("Bet Check v1 EPL portfolio currency is GBP")
    stake = _finite(bet.get("stake", 0.0), name="bet.stake")
    if stake < 0.0:
        raise ValueError("bet.stake must be >= 0")
    raw_legs = bet.get("legs")
    if not isinstance(raw_legs, list) or not raw_legs:
        raise ValueError("bet.legs must be a non-empty list")

    reference_by_event = _reference_map(references)
    legs: list[dict[str, Any]] = []
    for raw_leg in raw_legs:
        if not isinstance(raw_leg, Mapping):
            raise ValueError("Every bet leg must be an object")
        event_id = str(raw_leg.get("event_id") or "")
        if event_id not in reference_by_event:
            raise ValueError(f"No reference data for event_id: {event_id}")
        legs.append(evaluate_leg(raw_leg, reference_by_event[event_id]))

    leg_price_product = math.prod(float(leg["user_quote"]["decimal_odds"]) for leg in legs)
    raw_combined = bet.get("quoted_combined_odds")
    if raw_combined is None:
        user_combined_odds = leg_price_product
        combined_source = "product_of_leg_quotes"
    else:
        user_combined_odds = _decimal_odds(raw_combined, name="bet.quoted_combined_odds")
        combined_source = "user_supplied"

    combined = _combined_analysis(
        legs,
        user_combined_odds=user_combined_odds,
        leg_price_product=leg_price_product,
    )
    bet_type = "single" if len(legs) == 1 else "accumulator"
    return {
        "schema_version": 1,
        "status": "analysis_only_no_recommendation",
        "engine": "deterministic_local_bet_check_v1",
        "competition": "English Premier League",
        "currency": currency,
        "bet_type": bet_type,
        "stake": stake,
        "legs": legs,
        "weakest_leg": _weakest_leg(legs),
        "combined": {
            **combined,
            "combined_odds_source": combined_source,
            "potential_gross_return": stake * user_combined_odds,
            "maximum_cash_loss": stake,
        },
        "input_contract": {
            "ocr_required_by_core": False,
            "network_required_by_core": False,
            "fresh_data_may_require_network": True,
        },
        "governance": {
            "places_bet": False,
            "uses_llm": False,
            "cloud_reasoning_required": False,
            "positive_ev_is_recommendation": False,
            "same_event_joint_probability_supported": False,
        },
        "warning": (
            "Bet Check v1 explains price and probability structure. Football 1 model residuals and raw EV have not earned a validated betting threshold."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic Football 1 Bet Check on structured input.")
    parser.add_argument("--bet", type=Path, required=True, help="Structured bet JSON")
    parser.add_argument("--references", type=Path, required=True, help="Reference event JSON")
    parser.add_argument("--output", type=Path, default=Path("data/processed/bet_check.json"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    bet = json.loads(args.bet.read_text(encoding="utf-8"))
    references = json.loads(args.references.read_text(encoding="utf-8"))
    report = evaluate_bet(bet, references)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "bet_type": report["bet_type"],
                "legs": len(report["legs"]),
                "weakest_leg": report["weakest_leg"],
                "joint_probability_status": report["combined"]["joint_probability_status"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
