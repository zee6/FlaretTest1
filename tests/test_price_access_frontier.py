import pytest

from football1.price_access_frontier import build_price_matrix, evaluate_book_set, greedy_price_frontier


def _record(record_id: str, prices_a, prices_b, prices_c):
    return {
        "record_id": record_id,
        "status": "pre_kickoff_odds_snapshot",
        "event_id": record_id,
        "retrieved_at_utc": "2026-09-04T10:00:00+00:00",
        "home_team": "Home",
        "away_team": "Away",
        "bookmakers": [
            {"bookmaker_key": "a", "bookmaker_title": "A", "decimal_odds": dict(zip(("home", "draw", "away"), prices_a))},
            {"bookmaker_key": "b", "bookmaker_title": "B", "decimal_odds": dict(zip(("home", "draw", "away"), prices_b))},
            {"bookmaker_key": "c", "bookmaker_title": "C", "decimal_odds": dict(zip(("home", "draw", "away"), prices_c))},
            {"bookmaker_key": "smarkets", "bookmaker_title": "Smarkets", "decimal_odds": {"home": 9.0, "draw": 9.0, "away": 9.0}},
        ],
    }


def test_price_matrix_excludes_exchange_quotes() -> None:
    observations = build_price_matrix([_record("r1", (2.0, 3.0, 4.0), (2.1, 3.1, 3.9), (2.05, 3.05, 4.1))])
    assert len(observations) == 3
    assert "smarkets" not in observations[0]["quotes"]
    home = next(row for row in observations if row["outcome"] == "home")
    assert home["full_best_price"] == pytest.approx(2.1)


def test_evaluate_book_set_reports_closeness_not_only_exact_best() -> None:
    observations = build_price_matrix([_record("r1", (2.0, 3.0, 4.0), (2.1, 3.1, 3.9), (2.05, 3.05, 4.1))])
    metrics = evaluate_book_set(observations, ["a"])
    assert metrics["served_fraction"] == pytest.approx(1.0)
    assert metrics["exact_best_fraction"] == pytest.approx(1 / 3)
    assert metrics["mean_price_shortfall_vs_full_best"] > 0.0
    assert metrics["within_2pct_of_best_fraction"] < 1.0


def test_more_accounts_cannot_make_greedy_frontier_price_closeness_worse() -> None:
    records = [
        _record("r1", (2.0, 3.0, 4.0), (2.1, 3.1, 3.9), (2.05, 3.05, 4.1)),
        _record("r2", (1.9, 3.4, 4.2), (1.95, 3.3, 4.25), (2.0, 3.5, 4.1)),
    ]
    frontier = greedy_price_frontier(build_price_matrix(records))["frontier"]
    shortfalls = [row["mean_price_shortfall_vs_full_best"] for row in frontier]
    assert all(shortfalls[i + 1] <= shortfalls[i] + 1e-12 for i in range(len(shortfalls) - 1))
    assert frontier[-1]["mean_price_shortfall_vs_full_best"] == pytest.approx(0.0)
    assert frontier[-1]["exact_best_fraction"] == pytest.approx(1.0)
