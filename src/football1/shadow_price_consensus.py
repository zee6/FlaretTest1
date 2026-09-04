from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from football1.model_disagreement import (
    CLASS_ORDER,
    SHADOW_NAMES,
    DisagreementRow,
    build_disagreement_rows,
)


SUPPORT_EPSILON = 1e-12


@dataclass(frozen=True)
class PriceConsensusOpportunity:
    match_id: str
    season_start_year: int
    outcome: str
    market_rank: int
    market_probability: float
    decimal_odds: float
    shadow_probabilities: tuple[float, float, float, float]
    shadow_mean_probability: float
    shadow_mean_edge: float
    support_count: int
    won: bool

    @property
    def market_role(self) -> str:
        return "favorite" if self.market_rank == 1 else "non_favorite"


def _market_ranks(probs: tuple[float, float, float]) -> list[int]:
    order = sorted(range(3), key=lambda i: (-probs[i], i))
    ranks = [0, 0, 0]
    for rank, index in enumerate(order, start=1):
        ranks[index] = rank
    return ranks


def build_price_consensus_opportunities(
    rows: list[DisagreementRow],
) -> list[PriceConsensusOpportunity]:
    opportunities: list[PriceConsensusOpportunity] = []
    for row in rows:
        ranks = _market_ranks(row.market_probs)
        for index, outcome in enumerate(CLASS_ORDER):
            shadow_values = tuple(
                float(row.shadow_probs[name][index]) for name in SHADOW_NAMES
            )
            market_probability = float(row.market_probs[index])
            shadow_mean = sum(shadow_values) / len(shadow_values)
            support_count = sum(
                1
                for probability in shadow_values
                if probability > market_probability + SUPPORT_EPSILON
            )
            opportunities.append(
                PriceConsensusOpportunity(
                    match_id=row.match_id,
                    season_start_year=row.season_start_year,
                    outcome=outcome,
                    market_rank=ranks[index],
                    market_probability=market_probability,
                    decimal_odds=float(row.odds[index]),
                    shadow_probabilities=shadow_values,  # type: ignore[arg-type]
                    shadow_mean_probability=shadow_mean,
                    shadow_mean_edge=shadow_mean - market_probability,
                    support_count=support_count,
                    won=(row.result == outcome),
                )
            )
    return opportunities


def _group_metrics(
    opportunities: list[PriceConsensusOpportunity],
) -> dict[str, float | int | None]:
    if not opportunities:
        return {
            "opportunities": 0,
            "mean_market_probability": None,
            "observed_frequency": None,
            "calibration_gap_observed_minus_market": None,
            "mean_shadow_probability": None,
            "mean_shadow_edge": None,
            "mean_decimal_odds": None,
            "pnl_units": None,
            "roi": None,
        }

    n = len(opportunities)
    mean_market = sum(item.market_probability for item in opportunities) / n
    observed = sum(int(item.won) for item in opportunities) / n
    mean_shadow = sum(item.shadow_mean_probability for item in opportunities) / n
    pnl = sum(
        (item.decimal_odds - 1.0) if item.won else -1.0
        for item in opportunities
    )
    return {
        "opportunities": n,
        "mean_market_probability": mean_market,
        "observed_frequency": observed,
        "calibration_gap_observed_minus_market": observed - mean_market,
        "mean_shadow_probability": mean_shadow,
        "mean_shadow_edge": mean_shadow - mean_market,
        "mean_decimal_odds": sum(item.decimal_odds for item in opportunities) / n,
        "pnl_units": pnl,
        "roi": pnl / n,
    }


def _support_report(
    opportunities: list[PriceConsensusOpportunity],
) -> dict[str, object]:
    return {
        str(count): _group_metrics(
            [item for item in opportunities if item.support_count == count]
        )
        for count in range(5)
    }


def shadow_price_consensus_from_rows(
    rows: list[DisagreementRow],
) -> dict[str, object]:
    opportunities = build_price_consensus_opportunities(rows)
    seasons = sorted({item.season_start_year for item in opportunities})

    return {
        "experiment": "shadow_probability_residual_price_consensus_v1",
        "status": "historical_retrospective_observer_only_zero_decision_weight",
        "research_selection_status": (
            "Specified after inspecting the earlier shadow-disagreement and confidence "
            "observers. Results are exploratory and cannot be promoted without fresh "
            "prospective confirmation."
        ),
        "question": (
            "When several independently conceived OOS shadow models all put an outcome's "
            "probability above the de-vigged bookmaker market, does that sign consensus "
            "identify genuine underpricing rather than merely a different story?"
        ),
        "support_definition": (
            "For each match and each H/D/A outcome, support_count is the number of four OOS "
            "shadow models whose probability is strictly above the de-vigged B365 market "
            "probability. No edge-size threshold is selected."
        ),
        "shadow_models": list(SHADOW_NAMES),
        "opportunity_policy": (
            "All three outcomes from every OOS match are retained. Support counts 0..4 are "
            "reported in full; no profitable-looking subgroup is selected as a strategy."
        ),
        "decision_policy": (
            "Observer only. These groups do not alter Football 1 probabilities, create a bet, "
            "set a threshold, or change stake suitability."
        ),
        "all_outcomes_by_support_count": _support_report(opportunities),
        "favorites_by_support_count": _support_report(
            [item for item in opportunities if item.market_role == "favorite"]
        ),
        "non_favorites_by_support_count": _support_report(
            [item for item in opportunities if item.market_role == "non_favorite"]
        ),
        "seasons": [
            {
                "season_start_year": season,
                "all_outcomes_by_support_count": _support_report(
                    [item for item in opportunities if item.season_start_year == season]
                ),
            }
            for season in seasons
        ],
    }


def shadow_price_consensus_audit(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
) -> dict[str, object]:
    rows = build_disagreement_rows(db_path, min_train_seasons=min_train_seasons)
    return shadow_price_consensus_from_rows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Observe whether sign agreement among OOS shadow probability residuals "
            "identifies bookmaker underpricing."
        )
    )
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/football1.sqlite")
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = shadow_price_consensus_audit(
        args.database, min_train_seasons=args.min_train_seasons
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote shadow-price-consensus report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
