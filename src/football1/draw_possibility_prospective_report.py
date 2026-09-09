from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sklearn.metrics import roc_auc_score

from football1.draw_possibility_shadow import content_hash as shadow_content_hash
from football1.prospective import prediction_content_hash
from football1.settlement import settlement_content_hash


FLAG_KEYS = ("within_2pp", "within_5pp", "within_10pp")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _verify_prediction(row: dict[str, Any]) -> None:
    unsigned = dict(row)
    stored = unsigned.pop("content_sha256", None)
    if stored != prediction_content_hash(unsigned):
        raise ValueError(f"Prediction {row.get('record_id')} failed content hash verification")


def _verify_shadow(row: dict[str, Any]) -> None:
    unsigned = dict(row)
    stored = unsigned.pop("content_sha256", None)
    if stored != shadow_content_hash(unsigned):
        raise ValueError(f"Draw Possibility shadow {row.get('record_id')} failed content hash verification")
    if float(row.get("decision_weight", 1.0)) != 0.0:
        raise ValueError("Draw Possibility shadow must have zero decision weight")
    if row["draw_possibility"].get("is_probability") is not False:
        raise ValueError("Draw Possibility score must be explicitly marked as non-probability")


def _verify_settlement(row: dict[str, Any]) -> None:
    unsigned = dict(row)
    stored = unsigned.pop("content_sha256", None)
    if stored != settlement_content_hash(unsigned):
        raise ValueError(f"Settlement {row.get('settlement_id')} failed content hash verification")


def _auc(items: list[tuple[float, bool]]) -> float | None:
    if not items:
        return None
    positives = sum(int(actual) for _, actual in items)
    if positives == 0 or positives == len(items):
        return None
    return float(roc_auc_score([int(actual) for _, actual in items], [float(score) for score, _ in items]))


def _selection_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = [row for row in rows if row["settled"]]
    complete = len(settled) == len(rows)
    draws = sum(int(row["is_draw"]) for row in settled)
    pnl = sum(float(row["draw_unit_pnl_at_recorded_best"]) for row in settled)
    return {
        "selected": len(rows),
        "settled": len(settled),
        "complete": complete,
        "draws": draws,
        "draw_rate": draws / len(rows) if rows and complete else None,
        "gross_draw_pnl_units_at_recorded_best": pnl if complete else None,
        "gross_draw_roi_at_recorded_best": pnl / len(rows) if rows and complete else None,
        "events": [
            {
                "rank": row["possibility_rank"],
                "event_id": row["event_id"],
                "home": row["home"],
                "away": row["away"],
                "possibility": row["possibility"],
                "market_pdraw": row["market_pdraw"],
                "settled": row["settled"],
                "result": row["result"],
            }
            for row in rows
        ],
    }


def build_report(shadow_path: Path, prediction_path: Path, settlement_path: Path) -> dict[str, Any]:
    shadows = _load_jsonl(shadow_path)
    predictions = _load_jsonl(prediction_path)
    settlements = _load_jsonl(settlement_path)
    for row in shadows:
        _verify_shadow(row)
    for row in predictions:
        _verify_prediction(row)
    for row in settlements:
        _verify_settlement(row)

    shadow_ids = [str(row["record_id"]) for row in shadows]
    if len(set(shadow_ids)) != len(shadow_ids):
        raise ValueError("Duplicate Draw Possibility shadow record id")
    shadow_events = [str(row["event_id"]) for row in shadows]
    if len(set(shadow_events)) != len(shadow_events):
        raise ValueError("Duplicate Draw Possibility shadow event id")

    predictions_by_id = {str(row["record_id"]): row for row in predictions}
    settlements_by_prediction = {str(row["prediction_record_id"]): row for row in settlements}

    joined: list[dict[str, Any]] = []
    for shadow in shadows:
        source = shadow["source_prediction"]
        prediction_id = str(source["record_id"])
        prediction = predictions_by_id.get(prediction_id)
        if prediction is None:
            raise ValueError(f"Shadow references unknown prediction {prediction_id}")
        if str(source["content_sha256"]) != str(prediction["content_sha256"]):
            raise ValueError(f"Shadow prediction hash mismatch {prediction_id}")
        if str(shadow["event_id"]) != str(prediction["event_id"]):
            raise ValueError(f"Shadow event id mismatch {prediction_id}")

        market = shadow["market_probability"]
        original_market = prediction["market_anchor"]["probability"]
        for label in ("home", "draw", "away"):
            if abs(float(market[label]) - float(original_market[label])) > 1e-12:
                raise ValueError(f"Shadow market probability mismatch {prediction_id} {label}")

        settlement = settlements_by_prediction.get(prediction_id)
        if settlement is not None:
            if str(settlement["prediction_content_sha256"]) != str(prediction["content_sha256"]):
                raise ValueError(f"Settlement prediction hash mismatch {prediction_id}")
            if str(settlement["event_id"]) != str(shadow["event_id"]):
                raise ValueError(f"Settlement event id mismatch {prediction_id}")
            result = str(settlement["result"])
            is_draw = result == "draw"
            draw_odds = float(prediction["market_anchor"]["best_decimal_odds"]["draw"])
            draw_unit_pnl = draw_odds - 1.0 if is_draw else -1.0
        else:
            result = None
            is_draw = None
            draw_odds = float(prediction["market_anchor"]["best_decimal_odds"]["draw"])
            draw_unit_pnl = None

        joined.append(
            {
                "event_id": str(shadow["event_id"]),
                "home": str(shadow["teams"]["home"]),
                "away": str(shadow["teams"]["away"]),
                "commence_time_utc": str(shadow["commence_time_utc"]),
                "possibility": float(shadow["draw_possibility"]["balance_percentile_0_to_100"]),
                "home_away_gap": float(shadow["draw_possibility"]["home_away_probability_gap"]),
                "market_pdraw": float(market["draw"]),
                "flags": dict(shadow["draw_possibility"]["fixed_predeclared_balance_flags"]),
                "draw_odds": draw_odds,
                "settled": settlement is not None,
                "result": result,
                "is_draw": is_draw,
                "draw_unit_pnl_at_recorded_best": draw_unit_pnl,
            }
        )

    possibility_ranked = sorted(joined, key=lambda row: (-row["possibility"], row["event_id"]))
    for index, row in enumerate(possibility_ranked, start=1):
        row["possibility_rank"] = index

    market_ranked = sorted(joined, key=lambda row: (-row["market_pdraw"], row["event_id"]))
    market_rank_summary = [
        {
            "rank": index,
            "event_id": row["event_id"],
            "home": row["home"],
            "away": row["away"],
            "market_pdraw": row["market_pdraw"],
            "possibility": row["possibility"],
            "settled": row["settled"],
            "result": row["result"],
        }
        for index, row in enumerate(market_ranked, start=1)
    ]

    settled = [row for row in joined if row["settled"]]
    possibility_auc = _auc([(row["possibility"], bool(row["is_draw"])) for row in settled])
    market_auc = _auc([(row["market_pdraw"], bool(row["is_draw"])) for row in settled])

    fixed_groups = {
        key: _selection_summary([row for row in possibility_ranked if bool(row["flags"].get(key))])
        for key in FLAG_KEYS
    }

    return {
        "experiment": "prospective_draw_possibility_ranking_report_v1",
        "status": "prospective_zero_decision_weight",
        "shadow_records": len(shadows),
        "settled_shadow_records": len(settled),
        "all_shadow_settled": len(settled) == len(shadows),
        "ranking_metrics": {
            "possibility_auc_for_draw_on_settled": possibility_auc,
            "market_pdraw_auc_for_draw_on_settled": market_auc,
            "auc_delta_possibility_minus_market": (
                possibility_auc - market_auc
                if possibility_auc is not None and market_auc is not None
                else None
            ),
        },
        "predeclared_rank_summaries": {
            "top_1_draw_possibility": _selection_summary(possibility_ranked[:1]),
            "top_2_draw_possibility": _selection_summary(possibility_ranked[:2]),
            "fixed_balance_flags": fixed_groups,
        },
        "draw_possibility_ranking": possibility_ranked,
        "market_pdraw_ranking": market_rank_summary,
        "price_caveat": (
            "Gross draw P&L uses the best numeric quote stored in the original prediction lock. "
            "The original lock did not preserve bookmaker provenance for every best quote, so this is research-price P&L, not claimed executable sportsbook performance."
        ),
        "guardrails": [
            "Draw Possibility is a ranking score, not a probability.",
            "The top-1 and top-2 summaries are fixed before the 12-14 September results and must not be redefined after settlement.",
            "The 2pp, 5pp and 10pp flags are all retained; no winning historical cutoff may be selected retrospectively.",
            "No decision weight, betting threshold, probability override or staking rule follows from this report.",
            "A ten-match slate is evidence, not validation; later prospective slates must accumulate without changing the score definition."
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score the frozen prospective Draw Possibility ranking.")
    parser.add_argument("--shadow", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--settlements", type=Path, default=Path("prospective/settlements.jsonl"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(args.shadow, args.ledger, args.settlements)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote prospective Draw Possibility report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
