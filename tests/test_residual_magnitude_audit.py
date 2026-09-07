from __future__ import annotations

import pytest

from football1.market_baseline import RESULT_INDEX
from football1.residual_magnitude_audit import summarize_residual_records


LABELS = ("H", "D", "A")


def _record(
    *,
    match_id: str,
    market: tuple[float, float, float],
    model: tuple[float, float, float],
    result: str,
    season: int = 2020,
) -> dict:
    residual = tuple(model[i] - market[i] for i in range(3))
    selected = max(range(3), key=lambda i: residual[i])
    return {
        "match_id": match_id,
        "season_start_year": season,
        "match_date": f"{season}-09-01",
        "result": result,
        "market_probability": market,
        "model_probability": model,
        "probability_residual": residual,
        "max_abs_residual": max(abs(v) for v in residual),
        "l1_residual": sum(abs(v) for v in residual),
        "selected_outcome_index": selected,
        "selected_outcome": LABELS[selected],
        "selected_positive_shift": residual[selected],
        "selected_market_probability": market[selected],
        "selected_model_probability": model[selected],
        "selected_actual": int(RESULT_INDEX[result] == selected),
    }


def test_zero_residuals_have_zero_score_delta() -> None:
    records = [
        _record(
            match_id=str(i),
            market=(0.45, 0.28, 0.27),
            model=(0.45, 0.28, 0.27),
            result=("H", "D", "A")[i % 3],
            season=2020 + (i % 2),
        )
        for i in range(10)
    ]
    report = summarize_residual_records(records)

    assert report["matches"] == 10
    assert report["overall"]["log_loss_delta_model_minus_market"] == pytest.approx(0.0)
    assert report["overall"]["brier_delta_model_minus_market"] == pytest.approx(0.0)
    assert report["reference_quantiles"]["match_max_abs_residual"]["max"] == pytest.approx(0.0)


def test_residual_quintiles_partition_and_order_records() -> None:
    records = []
    for i in range(1, 11):
        shift = i / 1000.0
        records.append(
            _record(
                match_id=str(i),
                market=(0.40, 0.30, 0.30),
                model=(0.40 + shift, 0.30 - shift / 2.0, 0.30 - shift / 2.0),
                result="H" if i >= 6 else "A",
            )
        )

    report = summarize_residual_records(records)
    match_blocks = report["match_max_abs_residual_quintiles"]
    shift_blocks = report["selected_positive_shift_quintiles"]

    assert len(match_blocks) == 5
    assert sum(block["matches"] for block in match_blocks) == 10
    assert len(shift_blocks) == 5
    assert sum(block["matches"] for block in shift_blocks) == 10
    assert match_blocks[0]["max_value"] < match_blocks[-1]["min_value"]
    assert shift_blocks[0]["mean_positive_shift"] < shift_blocks[-1]["mean_positive_shift"]


def test_large_positive_shift_group_can_be_scored_without_becoming_a_threshold() -> None:
    records = []
    for i in range(1, 11):
        shift = i / 100.0
        records.append(
            _record(
                match_id=str(i),
                market=(0.40, 0.30, 0.30),
                model=(0.40 + shift, 0.30 - shift / 2.0, 0.30 - shift / 2.0),
                result="H" if i >= 9 else "A",
            )
        )

    report = summarize_residual_records(records)
    top = report["selected_positive_shift_quintiles"][-1]

    assert top["quintile"] == 5
    assert top["observed_rate"] == pytest.approx(1.0)
    assert top["brier_delta_model_minus_market"] < 0.0
    assert top["log_loss_delta_model_minus_market"] < 0.0
    # The report describes the group; it deliberately does not emit a cutoff or promotion flag.
    assert "threshold" not in report
    assert "promotion_allowed" not in report


def test_reference_quantiles_are_monotone() -> None:
    records = []
    for i in range(1, 21):
        shift = i / 1000.0
        records.append(
            _record(
                match_id=str(i),
                market=(0.40, 0.30, 0.30),
                model=(0.40 + shift, 0.30 - shift / 2.0, 0.30 - shift / 2.0),
                result="H",
            )
        )

    q = summarize_residual_records(records)["reference_quantiles"]["selected_positive_shift"]
    assert q["p50"] <= q["p75"] <= q["p90"] <= q["p95"] <= q["p99"] <= q["max"]
