from __future__ import annotations

from football1.confidence_observer import (
    _binary_metrics,
    _market_top_correct,
    _market_top_probability,
    walk_forward_confidence_from_rows,
)
from football1.model_disagreement import DisagreementRow


def _row(
    *,
    season: int,
    suffix: str,
    market_probs: tuple[float, float, float],
    result: str,
    alignment: int,
    consensus: int,
    dispersion: float = 0.03,
    distance: float = 0.04,
) -> DisagreementRow:
    market_top = ("H", "D", "A")[max(range(3), key=lambda i: market_probs[i])]
    shadow_probs = {
        "elo": market_probs,
        "bayesian_strength": market_probs,
        "poisson": market_probs,
        "dixon_coles": market_probs,
    }
    return DisagreementRow(
        match_id=f"{season}-{suffix}",
        season_start_year=season,
        match_date=f"{season}-09-01",
        home_team="Home",
        away_team="Away",
        result=result,
        market_probs=market_probs,
        odds=(2.0, 3.5, 4.0),
        shadow_probs=shadow_probs,
        shadow_mean_probs=market_probs,
        blended_probs=market_probs,
        market_top=market_top,
        shadow_consensus_top=market_top if consensus >= 3 else None,
        shadow_consensus_count=consensus,
        market_alignment_count=alignment,
        probability_dispersion=dispersion,
        mean_abs_shadow_market_distance=distance,
    )


def test_market_top_helpers() -> None:
    row = _row(
        season=2020,
        suffix="a",
        market_probs=(0.62, 0.23, 0.15),
        result="H",
        alignment=4,
        consensus=4,
    )
    assert _market_top_probability(row) == 0.62
    assert _market_top_correct(row) == 1


def test_binary_metrics_are_probability_metrics() -> None:
    metrics = _binary_metrics([0.8, 0.7, 0.3, 0.2], [1, 1, 0, 0])
    assert metrics["matches"] == 4
    assert metrics["log_loss"] is not None
    assert float(metrics["log_loss"]) < 0.4
    assert metrics["brier"] is not None
    assert float(metrics["brier"]) < 0.1
    assert metrics["accuracy"] == 1.0


def test_meta_walk_forward_uses_only_earlier_oos_seasons() -> None:
    rows: list[DisagreementRow] = []
    for season in range(2015, 2021):
        rows.extend(
            [
                _row(
                    season=season,
                    suffix="good",
                    market_probs=(0.62, 0.23, 0.15),
                    result="H",
                    alignment=4,
                    consensus=4,
                    dispersion=0.01,
                    distance=0.01,
                ),
                _row(
                    season=season,
                    suffix="miss",
                    market_probs=(0.56, 0.26, 0.18),
                    result="A",
                    alignment=1,
                    consensus=2,
                    dispersion=0.08,
                    distance=0.12,
                ),
            ]
        )

    report = walk_forward_confidence_from_rows(rows, meta_min_train_seasons=3)
    seasons = report["seasons"]
    assert [item["test_season_start_year"] for item in seasons] == [2018, 2019, 2020]
    assert seasons[0]["train_oos_seasons"] == [2015, 2016, 2017]
    assert 2018 not in seasons[0]["train_oos_seasons"]
    assert report["overall"]["raw_market_top_probability"]["matches"] == 6
    assert report["status"] == "historical_retrospective_observer_only_zero_decision_weight"
