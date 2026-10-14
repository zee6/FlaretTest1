"""Shared semantic checks for recorded prospective outcomes."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from football1.settlement import settlement_content_hash

LABELS = ("home", "draw", "away")


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Evidence timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_settlement_against_prediction(row: dict[str, Any], prediction: dict[str, Any]) -> None:
    unsigned = dict(row)
    stored = unsigned.pop("content_sha256", None)
    _require(stored == settlement_content_hash(unsigned), "Settlement hash mismatch")
    for key in ("event_id", "home_team_provider", "away_team_provider"):
        _require(row[key] == prediction[key], f"Settlement {key} mismatch")
    _require(row["prediction_content_sha256"] == prediction["content_sha256"],
             "Settlement prediction hash mismatch")
    _require(_time(row["scores_retrieved_at_utc"]) > _time(prediction["commence_time_utc"]),
             "Settlement retrieval must follow kickoff")
    home, away = row["home_score"], row["away_score"]
    _require(all(type(score) is int and score >= 0 for score in (home, away)),
             "Invalid final score")
    result = "home" if home > away else "away" if away > home else "draw"
    _require(row["result"] == result, "Settlement result disagrees with final score")
    for prefix, source in (("market", "market_anchor"), ("model", "model")):
        probability = prediction[source]["probability"]
        expected = {
            f"{prefix}_log_loss": -math.log(probability[result]),
            f"{prefix}_brier": sum((probability[label] - int(label == result)) ** 2 for label in LABELS),
        }
        for key, value in expected.items():
            _require(math.isclose(row[key], value, rel_tol=0, abs_tol=1e-10),
                     f"Settlement {key} disagrees with locked probabilities")
    odds = prediction["market_anchor"]["best_decimal_odds"]
    pnl = {label: odds[label] - 1 if label == result else -1.0 for label in LABELS}
    for label in LABELS:
        _require(math.isclose(row["unit_pnl_if_bet_at_recorded_best_odds"][label],
                             pnl[label], rel_tol=0, abs_tol=1e-10), "Settlement unit P&L mismatch")
    chosen = prediction["model"]["max_predicted_ev_outcome"]
    _require(row["recorded_max_ev_outcome"] == chosen, "Settlement EV selection mismatch")
    _require(math.isclose(row["recorded_max_ev"], prediction["model"]["max_predicted_ev"],
                         rel_tol=0, abs_tol=1e-10), "Settlement EV mismatch")
    _require(math.isclose(row["recorded_max_ev_selection_unit_pnl"], pnl[chosen],
                         rel_tol=0, abs_tol=1e-10), "Settlement selected P&L mismatch")
    _require(row["strategy_threshold"] is None, "No active strategy threshold is permitted")

