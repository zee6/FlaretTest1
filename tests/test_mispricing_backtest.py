import pytest

from football1.features import FeatureRow
from football1.mispricing_backtest import candidate_bet, max_drawdown, summarize_bets


def _row(result: str = "H") -> FeatureRow:
    return FeatureRow(
        match_id="m1",
        season_start_year=2025,
        match_date="2025-08-01",
        home_team="A",
        away_team="B",
        result=result,
        elo_diff=0.0,
        ppg5_diff=0.0,
        gf5_diff=0.0,
        ga5_diff=0.0,
        shots5_diff=0.0,
        shots_allowed5_diff=0.0,
        sot5_diff=0.0,
        sot_allowed5_diff=0.0,
        ppg10_diff=0.0,
        gf10_diff=0.0,
        ga10_diff=0.0,
        rest_days_diff=0.0,
        log_prior_games_home=3.0,
        log_prior_games_away=3.0,
        b365_home=2.0,
        b365_draw=4.0,
        b365_away=5.0,
    )


def test_candidate_bet_selects_only_maximum_ev_outcome():
    row = _row("A")
    # EVs: H=0.00, D=0.20, A=0.25 -> away selected.
    bet = candidate_bet(row, (0.50, 0.30, 0.25))
    assert bet.outcome == "A"
    assert bet.predicted_ev == pytest.approx(0.25)
    assert bet.won is True
    assert bet.pnl == pytest.approx(4.0)


def test_losing_bet_is_exactly_minus_one_unit():
    bet = candidate_bet(_row("H"), (0.20, 0.25, 0.30))
    assert bet.outcome == "A"
    assert bet.won is False
    assert bet.pnl == pytest.approx(-1.0)


def test_summary_pnl_roi_and_drawdown_sanity():
    bets = [
        candidate_bet(_row("A"), (0.20, 0.25, 0.30)),  # +4.0
        candidate_bet(FeatureRow(**{**_row("H").__dict__, "match_id": "m2"}), (0.20, 0.25, 0.30)),  # -1
        candidate_bet(FeatureRow(**{**_row("H").__dict__, "match_id": "m3"}), (0.20, 0.25, 0.30)),  # -1
    ]
    summary = summarize_bets(bets)
    assert summary["stake_units"] == pytest.approx(3.0)
    assert summary["pnl_units"] == pytest.approx(2.0)
    assert summary["roi"] == pytest.approx(2.0 / 3.0)
    assert summary["max_drawdown_units"] == pytest.approx(2.0)


def test_max_drawdown_uses_running_pnl_not_final_loss_only():
    assert max_drawdown([2.0, -1.0, -1.0, 3.0, -1.0]) == pytest.approx(2.0)
