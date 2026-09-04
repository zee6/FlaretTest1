from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from football1.features import FeatureRow, build_feature_rows
from football1.offset_slant import fit_offset_slant


OUTCOMES = ("H", "D", "A")
DEFAULT_THRESHOLDS = (0.025, 0.05, 0.075, 0.10)


@dataclass(frozen=True)
class Bet:
    match_id: str
    season_start_year: int
    match_date: str
    outcome: str
    odds: float
    model_probability: float
    predicted_ev: float
    won: bool
    pnl: float


def _quoted_odds(row: FeatureRow) -> tuple[float, float, float]:
    values = (row.b365_home, row.b365_draw, row.b365_away)
    if any(value is None or value <= 1.0 for value in values):
        raise ValueError(f"Missing/invalid Bet365 odds for {row.match_id}")
    return values  # type: ignore[return-value]


def candidate_bet(row: FeatureRow, probs: tuple[float, float, float]) -> Bet:
    odds = _quoted_odds(row)
    evs = tuple(probs[i] * odds[i] - 1.0 for i in range(3))
    best_index = max(range(3), key=lambda i: evs[i])
    outcome = OUTCOMES[best_index]
    won = row.result == outcome
    pnl = (odds[best_index] - 1.0) if won else -1.0
    return Bet(
        match_id=row.match_id,
        season_start_year=row.season_start_year,
        match_date=row.match_date,
        outcome=outcome,
        odds=odds[best_index],
        model_probability=probs[best_index],
        predicted_ev=evs[best_index],
        won=won,
        pnl=pnl,
    )


def max_drawdown(pnls: list[float]) -> float:
    balance = 0.0
    peak = 0.0
    drawdown = 0.0
    for pnl in pnls:
        balance += pnl
        peak = max(peak, balance)
        drawdown = max(drawdown, peak - balance)
    return drawdown


def summarize_bets(bets: list[Bet]) -> dict[str, object]:
    if not bets:
        return {
            "bets": 0,
            "wins": 0,
            "hit_rate": None,
            "mean_odds": None,
            "mean_predicted_ev": None,
            "stake_units": 0.0,
            "pnl_units": 0.0,
            "roi": None,
            "max_drawdown_units": 0.0,
            "by_outcome": {},
            "by_season": {},
        }

    stake = float(len(bets))
    pnl = sum(b.pnl for b in bets)
    by_outcome: dict[str, dict[str, float | int]] = {}
    for outcome in OUTCOMES:
        subset = [b for b in bets if b.outcome == outcome]
        if subset:
            sub_pnl = sum(b.pnl for b in subset)
            by_outcome[outcome] = {
                "bets": len(subset),
                "wins": sum(b.won for b in subset),
                "pnl_units": sub_pnl,
                "roi": sub_pnl / len(subset),
                "mean_odds": sum(b.odds for b in subset) / len(subset),
                "mean_predicted_ev": sum(b.predicted_ev for b in subset) / len(subset),
            }

    by_season: dict[str, dict[str, float | int]] = {}
    for season in sorted({b.season_start_year for b in bets}):
        subset = [b for b in bets if b.season_start_year == season]
        sub_pnl = sum(b.pnl for b in subset)
        by_season[str(season)] = {
            "bets": len(subset),
            "wins": sum(b.won for b in subset),
            "pnl_units": sub_pnl,
            "roi": sub_pnl / len(subset),
        }

    return {
        "bets": len(bets),
        "wins": sum(b.won for b in bets),
        "hit_rate": sum(b.won for b in bets) / len(bets),
        "mean_odds": sum(b.odds for b in bets) / len(bets),
        "mean_predicted_ev": sum(b.predicted_ev for b in bets) / len(bets),
        "stake_units": stake,
        "pnl_units": pnl,
        "roi": pnl / stake,
        "max_drawdown_units": max_drawdown([b.pnl for b in bets]),
        "by_outcome": by_outcome,
        "by_season": by_season,
    }


def walk_forward_mispricing_backtest(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
    alpha: float = 0.10,
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS,
) -> dict[str, object]:
    """Exploratory tail test using one maximum-EV flat-stake bet per match.

    Model specification and alpha are inherited unchanged from the already
    evaluated fixed-market residual model. Thresholds are a pre-declared
    sensitivity grid; every threshold is reported and none is selected as
    "best" by this function.
    """
    if any(t < 0 for t in thresholds):
        raise ValueError("thresholds must be non-negative")
    if tuple(sorted(set(thresholds))) != thresholds:
        raise ValueError("thresholds must be unique and increasing")

    rows = build_feature_rows(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    all_candidates: list[Bet] = []

    for test_index in range(min_train_seasons, len(seasons)):
        train = [r for r in rows if r.season_start_year in seasons[:test_index]]
        test = [r for r in rows if r.season_start_year == seasons[test_index]]
        model = fit_offset_slant(train, alpha=alpha)
        for row in test:
            all_candidates.append(candidate_bet(row, model.predict(row)))

    if len({bet.match_id for bet in all_candidates}) != len(all_candidates):
        raise RuntimeError("Duplicate match detected in OOS candidate set")

    reports: list[dict[str, object]] = []
    for threshold in thresholds:
        selected = [bet for bet in all_candidates if bet.predicted_ev >= threshold]
        if any(b.predicted_ev + 1e-12 < threshold for b in selected):
            raise RuntimeError("Threshold selection integrity failure")
        reports.append(
            {
                "threshold": threshold,
                **summarize_bets(selected),
            }
        )

    return {
        "model": "fixed_market_offset_football_slant_v1",
        "alpha": alpha,
        "market_source": "B365 pre-closing quoted decimal odds",
        "bet_rule": "at most one bet per match: outcome with maximum model EV; flat stake 1 unit if EV >= threshold",
        "ev_formula": "model_probability * decimal_odds - 1",
        "pnl_formula": "win: decimal_odds - 1; loss: -1",
        "threshold_policy": "fixed sensitivity grid; report all thresholds; do not select best ex post",
        "thresholds": list(thresholds),
        "oos_matches": len(all_candidates),
        "results": reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Flat-stake OOS tail test for Football 1 market mispricing signals.")
    parser.add_argument("--database", type=Path, default=Path("data/processed/football1.sqlite"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    parser.add_argument("--alpha", type=float, default=0.10)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_mispricing_backtest(
        args.database,
        min_train_seasons=args.min_train_seasons,
        alpha=args.alpha,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote mispricing tail backtest to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
