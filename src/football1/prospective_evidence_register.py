from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from football1.prospective import prediction_content_hash
from football1.prospective_consensus_movement import movement_forecast_content_hash
from football1.settlement import settlement_content_hash


LANE_IDS = (
    "primary_probability",
    "general_recency",
    "draw_possibility",
    "movement",
    "portfolio",
)

ARTIFACT_PINS = {
    "recency_30d_shadow": {
        "run_id": 34335029540,
        "name": "epl-prospective-recency-shadow",
        "sha256": "28de0ae556d1e9f24ee7491118a7ab06ba439563a808b6f49eaa7a581120400c",
    },
    "recency_15d_shadow": {
        "run_id": 34337404778,
        "name": "epl-prospective-recency-shadow-15d",
        "sha256": "c3fcbe7ebd207f3fffd19f0b07b1bf2d3ed763d2343b7e7c59055f589729aef5",
    },
    "draw_possibility_shadow": {
        "run_id": 34345280458,
        "name": "epl-prospective-draw-possibility-shadow",
        "sha256": "915b174364b631db6fcdfb6e675855dcf527ec18e214daea701ee7d7d6db17ed",
    },
}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_predictions(rows: list[dict[str, Any]]) -> None:
    seen_ids: set[str] = set()
    seen_events: set[str] = set()
    for line_number, row in enumerate(rows, start=1):
        record_id = str(row.get("record_id", ""))
        event_id = str(row.get("event_id", ""))
        if not record_id or record_id in seen_ids:
            raise ValueError(f"Invalid or duplicate prediction record id on line {line_number}")
        if not event_id or event_id in seen_events:
            raise ValueError(f"Invalid or duplicate prediction event id on line {line_number}")
        unsigned = dict(row)
        stored = unsigned.pop("content_sha256", None)
        if stored != prediction_content_hash(unsigned):
            raise ValueError(f"Prediction line {line_number} failed content hash verification")
        seen_ids.add(record_id)
        seen_events.add(event_id)


def _verify_settlements(rows: list[dict[str, Any]], predictions_by_id: dict[str, dict[str, Any]]) -> None:
    seen_prediction_ids: set[str] = set()
    for line_number, row in enumerate(rows, start=1):
        prediction_id = str(row.get("prediction_record_id", ""))
        if not prediction_id or prediction_id in seen_prediction_ids:
            raise ValueError(f"Invalid or duplicate settlement prediction id on line {line_number}")
        unsigned = dict(row)
        stored = unsigned.pop("content_sha256", None)
        if stored != settlement_content_hash(unsigned):
            raise ValueError(f"Settlement line {line_number} failed content hash verification")
        prediction = predictions_by_id.get(prediction_id)
        if prediction is None:
            raise ValueError(f"Settlement references unknown prediction {prediction_id}")
        if str(row.get("prediction_content_sha256")) != str(prediction.get("content_sha256")):
            raise ValueError(f"Settlement prediction hash mismatch for {prediction_id}")
        seen_prediction_ids.add(prediction_id)


def _verify_movement(rows: list[dict[str, Any]]) -> None:
    seen_ids: set[str] = set()
    for line_number, row in enumerate(rows, start=1):
        record_id = str(row.get("record_id", ""))
        if not record_id or record_id in seen_ids:
            raise ValueError(f"Invalid or duplicate movement record id on line {line_number}")
        unsigned = dict(row)
        stored = unsigned.pop("content_sha256", None)
        if stored != movement_forecast_content_hash(unsigned):
            raise ValueError(f"Movement line {line_number} failed content hash verification")
        if float(row.get("decision_weight", 1.0)) != 0.0:
            raise ValueError("Prospective movement records must have zero decision weight")
        seen_ids.add(record_id)


def _stage(total: int, settled: int) -> str:
    if total < 0 or settled < 0 or settled > total:
        raise ValueError("Invalid total/settled counts")
    if total == 0 or settled == 0:
        return "prospective_frozen"
    if settled < total:
        return "prospective_partial"
    return "prospective_complete"


def _lane(
    *,
    lane_id: str,
    question: str,
    frozen_object: str,
    judging_metrics: list[str],
    stage: str,
    state: dict[str, Any],
    prohibited: list[str],
    historical_status: str,
    promotion_eligible: bool = False,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "lane_id": lane_id,
        "decision_weight": 0.0,
        "question": question,
        "frozen_object": frozen_object,
        "judging_metrics": judging_metrics,
        "evidence_stage": stage,
        "historical_status": historical_status,
        "promotion_eligible_from_current_register": promotion_eligible,
        "state": state,
        "prohibited_changes": prohibited,
        "notes": list(notes or []),
    }


def build_register(
    ledger_path: Path,
    settlement_path: Path,
    movement_path: Path,
    *,
    primary_report: dict[str, Any] | None = None,
    recency_report: dict[str, Any] | None = None,
    draw_report: dict[str, Any] | None = None,
    portfolio_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    predictions = _load_jsonl(ledger_path)
    settlements = _load_jsonl(settlement_path)
    movement = _load_jsonl(movement_path)
    _verify_predictions(predictions)
    by_id = {str(row["record_id"]): row for row in predictions}
    _verify_settlements(settlements, by_id)
    _verify_movement(movement)

    settled_ids = {str(row["prediction_record_id"]) for row in settlements}
    unsettled_predictions = [row for row in predictions if str(row["record_id"]) not in settled_ids]

    primary_state: dict[str, Any] = {
        "prediction_records": len(predictions),
        "settled_records": len(settlements),
        "unsettled_records": len(unsettled_predictions),
        "model_ids": sorted({str(row["model"]["id"]) for row in predictions}),
    }
    if primary_report is not None:
        if int(primary_report["prediction_records"]) != len(predictions):
            raise ValueError("Primary report prediction count does not match ledger")
        if int(primary_report["settled_records"]) != len(settlements):
            raise ValueError("Primary report settlement count does not match settlements")
        primary_state["current_probability_scoring"] = primary_report["probability_scoring"]

    recency_state: dict[str, Any]
    recency_stage = "prospective_frozen"
    if recency_report is None:
        recency_state = {"report_loaded": False, "artifact_pins": ["recency_30d_shadow", "recency_15d_shadow"]}
    else:
        total = int(recency_report["shadow_event_count"])
        settled = int(recency_report["settled_common_event_count"])
        if total != 10:
            raise ValueError("Expected the frozen recency comparison to contain 10 events")
        recency_stage = _stage(total, settled)
        recency_state = {
            "report_loaded": True,
            "shadow_event_count": total,
            "settled_common_event_count": settled,
            "unsettled_shadow_event_count": int(recency_report["unsettled_shadow_event_count"]),
            "model_ids": sorted(row["model_id"] for row in recency_report["shadow_files"]),
            "artifact_pins": ["recency_30d_shadow", "recency_15d_shadow"],
        }

    draw_state: dict[str, Any]
    draw_stage = "prospective_frozen"
    if draw_report is None:
        draw_state = {"report_loaded": False, "artifact_pins": ["draw_possibility_shadow"]}
    else:
        total = int(draw_report["shadow_records"])
        settled = int(draw_report["settled_shadow_records"])
        if total != 10:
            raise ValueError("Expected the frozen Draw Possibility shadow to contain 10 events")
        draw_stage = _stage(total, settled)
        top2 = draw_report["predeclared_rank_summaries"]["top_2_draw_possibility"]["events"]
        draw_state = {
            "report_loaded": True,
            "shadow_event_count": total,
            "settled_shadow_event_count": settled,
            "top_2_frozen_events": [
                {
                    "home": row["home"],
                    "away": row["away"],
                    "rank": row["rank"],
                    "internal_balance_rank_0_to_100": row["possibility"],
                }
                for row in top2
            ],
            "artifact_pins": ["draw_possibility_shadow"],
        }

    movement_state = {
        "locked_records": len(movement),
        "decision_weight_values": sorted({float(row["decision_weight"]) for row in movement}),
        "model_suite_ids": sorted({str(row["model_suite_id"]) for row in movement}),
        "note": "Outcome settlement is not itself sufficient to score price movement; a comparable later odds snapshot is required.",
    }

    portfolio_state: dict[str, Any] = {"report_loaded": portfolio_report is not None}
    if portfolio_report is not None:
        if int(portfolio_report["settled_records"]) != len(settlements):
            raise ValueError("Portfolio report settlement count does not match settlements")
        official = portfolio_report["official_research_portfolio"]
        if official["policy"] != "no_validated_betting_rule":
            raise ValueError("Official prospective portfolio policy changed unexpectedly")
        if int(official["portfolio"]["bets_placed"]) != 0:
            raise ValueError("Official prospective research portfolio must place zero compulsory bets")
        portfolio_state.update(
            {
                "settled_records": int(portfolio_report["settled_records"]),
                "official_policy": official["policy"],
                "official_bets_placed": int(official["portfolio"]["bets_placed"]),
                "shadow_selection_counts": portfolio_report["shadow_selection_counts"],
            }
        )

    lanes = [
        _lane(
            lane_id="primary_probability",
            question="Does the frozen Football 1 market-anchored probability estimate outperform the recorded live market consensus prospectively?",
            frozen_object="prospective/ledger.jsonl immutable prediction records",
            judging_metrics=["multiclass_log_loss", "multiclass_brier", "argmax_accuracy_secondary"],
            stage=_stage(len(predictions), len(settlements)),
            state=primary_state,
            historical_status="retained_fixed_market_residual_did_not_beat_market_overall_historically",
            prohibited=[
                "hindsight_threshold_selection",
                "model_weight_change_from_one_batch",
                "raw_positive_ev_as_validated_betting_rule",
            ],
        ),
        _lane(
            lane_id="general_recency",
            question="Does heavier weighting of recent general form improve the market-anchored model prospectively?",
            frozen_object="separate 30-day and 15-day zero-weight shadows on the identical 12-14 September event set",
            judging_metrics=["common_sample_multiclass_log_loss", "common_sample_multiclass_brier", "accuracy_secondary"],
            stage=recency_stage,
            state=recency_state,
            historical_status="15d_marginal_historical_lead_is_post_hoc_and_all_recency_variants_still_lost_to_market",
            prohibited=[
                "replace_30d_shadow_retroactively",
                "choose_half_life_from_one_10_match_batch",
                "activate_probability_weight",
                "stake_change",
            ],
        ),
        _lane(
            lane_id="draw_possibility",
            question="Can H/A market balance identify draw-prone match structure as a ranking clue without altering Draw probability?",
            frozen_object="12-14 September Draw Possibility rank plus fixed 2pp/5pp/10pp balance flags",
            judging_metrics=["ranking_auc", "predeclared_top_group_draw_rate_when_complete", "descriptive_research_price_pnl_when_complete"],
            stage=draw_stage,
            state=draw_state,
            historical_status="credible_post_hoc_structural_clue_not_historical_statistical_proof_and_not_probability_improvement",
            prohibited=[
                "draw_probability_override",
                "betting_threshold",
                "stake_rule",
                "confidence_claim",
                "interpret_internal_0_to_100_rank_as_probability_or_recommendation",
            ],
            notes=[
                "The internal 0-100 rank is preserved for research now; future UI must not make it look like a probability, confidence score or nap/recommendation."
            ],
        ),
        _lane(
            lane_id="movement",
            question="Can a frozen timing forecast improve obtainable entry price relative to acting immediately?",
            frozen_object="immutable movement predictions plus timestamped odds snapshots",
            judging_metrics=["common_bookmaker_movement_error", "direction_secondary", "obtainable_price_improvement", "opportunity_lost_by_waiting"],
            stage="prospective_frozen",
            state=movement_state,
            historical_status="football1_residual_failed_to_predict_historical_closing_movement",
            prohibited=[
                "activate_act_now_or_wait_without_prospective_support",
                "retrospective_snapshot_choice",
                "bookmaker_composition_change_as_market_movement",
            ],
        ),
        _lane(
            lane_id="portfolio",
            question="What capital consequences arise under predeclared risk controls and descriptive shadow selections?",
            frozen_object="official zero-compulsory-bet policy plus counterfactual shadow portfolio definitions",
            judging_metrics=["bankroll_path", "turnover", "roi", "max_drawdown", "losing_streak", "exposure"],
            stage="prospective_partial" if settlements else "prospective_frozen",
            state=portfolio_state,
            historical_status="risk_controls_reduced_capital_damage_but_did_not_create_edge",
            prohibited=[
                "portfolio_pnl_feedback_into_match_probability",
                "loss_chasing",
                "promote_shadow_strategy_from_one_matchweek",
                "conviction_upside_activation_without_validation",
            ],
        ),
    ]

    if tuple(row["lane_id"] for row in lanes) != LANE_IDS:
        raise AssertionError("Evidence lane order drifted")
    if any(float(row["decision_weight"]) != 0.0 for row in lanes):
        raise AssertionError("Evidence register cannot activate decision weight")
    if any(bool(row["promotion_eligible_from_current_register"]) for row in lanes):
        raise AssertionError("Evidence register cannot promote a lane")

    return {
        "register_id": "football1_prospective_evidence_register_v1",
        "status": "read_only_research_governance",
        "decision_weight": 0.0,
        "master_score": None,
        "aggregation_policy": "prohibited_incompatible_evidence_lanes_must_not_be_collapsed_into_one_confidence_score",
        "artifact_pins": ARTIFACT_PINS,
        "lanes": lanes,
        "core_rule": "Evidence may move between stages. Definitions do not move after the result.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Football 1 prospective evidence register.")
    parser.add_argument("--ledger", type=Path, default=Path("prospective/ledger.jsonl"))
    parser.add_argument("--settlements", type=Path, default=Path("prospective/settlements.jsonl"))
    parser.add_argument("--movement", type=Path, default=Path("prospective/movement_predictions.jsonl"))
    parser.add_argument("--primary-report", type=Path)
    parser.add_argument("--recency-report", type=Path)
    parser.add_argument("--draw-report", type=Path)
    parser.add_argument("--portfolio-report", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    register = build_register(
        args.ledger,
        args.settlements,
        args.movement,
        primary_report=_load_optional_json(args.primary_report),
        recency_report=_load_optional_json(args.recency_report),
        draw_report=_load_optional_json(args.draw_report),
        portfolio_report=_load_optional_json(args.portfolio_report),
    )
    text = json.dumps(register, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote prospective evidence register to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
