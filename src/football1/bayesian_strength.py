from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from football1.market_baseline import devig_decimal_odds, score_probabilities


CLASS_ORDER = ("H", "D", "A")

# v1 state-space assumptions. These are deliberately fixed before OOS evaluation.
HOME_ADVANTAGE_GOALS = 0.35
PRIOR_VARIANCE = 1.00
OBSERVATION_VARIANCE = 2.25
PROCESS_VARIANCE_PER_DAY = 0.0008
SEASON_CARRY = 0.80
SEASON_RESET_VARIANCE = 0.20
REGIME_DECAY = 0.75


@dataclass(frozen=True)
class BayesianStrengthRow:
    match_id: str
    season_start_year: int
    match_date: str
    home_team: str
    away_team: str
    result: str
    home_goals: int
    away_goals: int
    home_mean: float
    away_mean: float
    home_sd: float
    away_sd: float
    expected_goal_diff: float
    latent_diff_sd: float
    predictive_goal_diff_sd: float
    home_regime: float
    away_regime: float
    regime_diff: float
    market_probs: tuple[float, float, float] | None


@dataclass(frozen=True)
class BayesianStrengthHistoryPoint:
    match_id: str
    season_start_year: int
    match_date: str
    team: str
    opponent: str
    venue: str
    pre_match_mean: float
    pre_match_sd: float
    pre_match_regime: float


def _parse_market_probs(raw_json: str) -> tuple[float, float, float] | None:
    raw = json.loads(raw_json)
    try:
        odds = tuple(
            float(str(raw.get(name, "")).strip())
            for name in ("B365H", "B365D", "B365A")
        )
    except (TypeError, ValueError):
        return None
    if any((not math.isfinite(x)) or x <= 1.0 for x in odds):
        return None
    return devig_decimal_odds(odds)[0]  # type: ignore[arg-type]


def _parse_goals(raw_json: str) -> tuple[int, int]:
    raw = json.loads(raw_json)
    try:
        home = int(float(str(raw.get("FTHG", "")).strip()))
        away = int(float(str(raw.get("FTAG", "")).strip()))
    except (TypeError, ValueError) as exc:
        raise ValueError("Missing or invalid FTHG/FTAG in canonical raw_json") from exc
    if home < 0 or away < 0:
        raise ValueError("Goals cannot be negative")
    return home, away


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _expand_state(
    team: str,
    team_index: dict[str, int],
    mean: np.ndarray,
    covariance: np.ndarray,
    *,
    prior_variance: float,
) -> tuple[np.ndarray, np.ndarray]:
    if team in team_index:
        return mean, covariance
    index = len(team_index)
    team_index[team] = index
    mean = np.pad(mean, (0, 1), mode="constant")
    old_n = covariance.shape[0]
    expanded = np.zeros((old_n + 1, old_n + 1), dtype=float)
    if old_n:
        expanded[:old_n, :old_n] = covariance
    expanded[index, index] = prior_variance
    return mean, expanded


def _season_transition(
    mean: np.ndarray,
    covariance: np.ndarray,
    *,
    season_carry: float,
    season_reset_variance: float,
) -> tuple[np.ndarray, np.ndarray]:
    if not 0.0 <= season_carry <= 1.0:
        raise ValueError("season_carry must be between 0 and 1")
    if season_reset_variance < 0.0:
        raise ValueError("season_reset_variance must be non-negative")
    if mean.size == 0:
        return mean, covariance
    transitioned_mean = season_carry * mean
    transitioned_covariance = (
        (season_carry**2) * covariance
        + np.eye(mean.size, dtype=float) * season_reset_variance
    )
    return transitioned_mean, transitioned_covariance


def _apply_process_noise(
    covariance: np.ndarray,
    elapsed_days: int,
    *,
    process_variance_per_day: float,
) -> np.ndarray:
    if elapsed_days <= 0 or covariance.size == 0:
        return covariance
    if process_variance_per_day < 0.0:
        raise ValueError("process_variance_per_day must be non-negative")
    return covariance + np.eye(covariance.shape[0], dtype=float) * (
        elapsed_days * process_variance_per_day
    )


def _fixture_vector(home_index: int, away_index: int, n_teams: int) -> np.ndarray:
    x = np.zeros(n_teams, dtype=float)
    x[home_index] = 1.0
    x[away_index] = -1.0
    return x


def _kalman_match_update(
    mean: np.ndarray,
    covariance: np.ndarray,
    *,
    home_index: int,
    away_index: int,
    observed_goal_diff: float,
    home_advantage_goals: float,
    observation_variance: float,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Exact linear-Gaussian update for the stated goal-difference model.

    Observation model:
        goal_diff = home_advantage + home_strength - away_strength + noise
    where noise is Gaussian with fixed variance.
    """
    if observation_variance <= 0.0:
        raise ValueError("observation_variance must be positive")
    x = _fixture_vector(home_index, away_index, mean.size)
    expected = home_advantage_goals + float(x @ mean)
    latent_variance = float(x @ covariance @ x)
    innovation_variance = latent_variance + observation_variance
    innovation = observed_goal_diff - expected
    gain = (covariance @ x) / innovation_variance
    updated_mean = mean + gain * innovation
    updated_covariance = covariance - np.outer(gain, x @ covariance)
    updated_covariance = 0.5 * (updated_covariance + updated_covariance.T)
    surprise_z = innovation / math.sqrt(innovation_variance)
    return updated_mean, updated_covariance, innovation, surprise_z


def build_bayesian_strength_history(
    db_path: Path,
    *,
    home_advantage_goals: float = HOME_ADVANTAGE_GOALS,
    prior_variance: float = PRIOR_VARIANCE,
    observation_variance: float = OBSERVATION_VARIANCE,
    process_variance_per_day: float = PROCESS_VARIANCE_PER_DAY,
    season_carry: float = SEASON_CARRY,
    season_reset_variance: float = SEASON_RESET_VARIANCE,
    regime_decay: float = REGIME_DECAY,
) -> tuple[
    list[BayesianStrengthRow],
    dict[str, tuple[float, float]],
    list[BayesianStrengthHistoryPoint],
    dict[str, float],
]:
    """Build leakage-safe pre-match dynamic Bayesian strength states.

    The latent team state is Gaussian. Goal difference is the noisy linear
    observation, so posterior updates are Kalman updates under the stated model.
    All fixtures on the same date are snapshotted before any result from that
    date is allowed to update the state.

    The regime signal is a pre-match exponentially weighted history of signed
    standardized forecast surprises. It is diagnostic/candidate context only.
    """
    if prior_variance <= 0.0:
        raise ValueError("prior_variance must be positive")
    if not 0.0 <= regime_decay < 1.0:
        raise ValueError("regime_decay must be in [0, 1)")

    conn = sqlite3.connect(db_path)
    try:
        records = conn.execute(
            """
            SELECT match_id, season_start_year, match_date,
                   home_team, away_team, ftr, raw_json
            FROM matches
            ORDER BY season_start_year, match_date, match_id
            """
        ).fetchall()
    finally:
        conn.close()

    team_index: dict[str, int] = {}
    mean = np.zeros(0, dtype=float)
    covariance = np.zeros((0, 0), dtype=float)
    regime: dict[str, float] = {}
    rows: list[BayesianStrengthRow] = []
    history: list[BayesianStrengthHistoryPoint] = []
    current_season: int | None = None
    previous_date: date | None = None
    i = 0

    while i < len(records):
        season = int(records[i][1])
        date_text = str(records[i][2])
        current_date = _parse_date(date_text)

        if current_season != season:
            if current_season is not None:
                mean, covariance = _season_transition(
                    mean,
                    covariance,
                    season_carry=season_carry,
                    season_reset_variance=season_reset_variance,
                )
                regime = {
                    team: value * season_carry for team, value in regime.items()
                }
            current_season = season

        if previous_date is not None:
            elapsed = max((current_date - previous_date).days, 0)
            covariance = _apply_process_noise(
                covariance,
                elapsed,
                process_variance_per_day=process_variance_per_day,
            )
        previous_date = current_date

        j = i
        day_records: list[tuple[object, ...]] = []
        while (
            j < len(records)
            and int(records[j][1]) == season
            and str(records[j][2]) == date_text
        ):
            day_records.append(records[j])
            j += 1

        for record in day_records:
            home = str(record[3])
            away = str(record[4])
            mean, covariance = _expand_state(
                home,
                team_index,
                mean,
                covariance,
                prior_variance=prior_variance,
            )
            mean, covariance = _expand_state(
                away,
                team_index,
                mean,
                covariance,
                prior_variance=prior_variance,
            )
            regime.setdefault(home, 0.0)
            regime.setdefault(away, 0.0)

        snapshots: list[dict[str, object]] = []
        for record in day_records:
            (
                match_id,
                season_start_year,
                match_date,
                home_obj,
                away_obj,
                result_obj,
                raw_json_obj,
            ) = record
            home = str(home_obj)
            away = str(away_obj)
            result = str(result_obj)
            raw_json = str(raw_json_obj)
            home_goals, away_goals = _parse_goals(raw_json)
            hi = team_index[home]
            ai = team_index[away]
            x = _fixture_vector(hi, ai, mean.size)
            latent_variance = max(float(x @ covariance @ x), 0.0)
            predictive_variance = latent_variance + observation_variance
            home_mean = float(mean[hi])
            away_mean = float(mean[ai])
            home_sd = math.sqrt(max(float(covariance[hi, hi]), 0.0))
            away_sd = math.sqrt(max(float(covariance[ai, ai]), 0.0))
            expected_goal_diff = home_advantage_goals + home_mean - away_mean
            home_regime = float(regime[home])
            away_regime = float(regime[away])

            rows.append(
                BayesianStrengthRow(
                    match_id=str(match_id),
                    season_start_year=int(season_start_year),
                    match_date=str(match_date),
                    home_team=home,
                    away_team=away,
                    result=result,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    home_mean=home_mean,
                    away_mean=away_mean,
                    home_sd=home_sd,
                    away_sd=away_sd,
                    expected_goal_diff=expected_goal_diff,
                    latent_diff_sd=math.sqrt(latent_variance),
                    predictive_goal_diff_sd=math.sqrt(predictive_variance),
                    home_regime=home_regime,
                    away_regime=away_regime,
                    regime_diff=home_regime - away_regime,
                    market_probs=_parse_market_probs(raw_json),
                )
            )
            history.extend(
                [
                    BayesianStrengthHistoryPoint(
                        match_id=str(match_id),
                        season_start_year=int(season_start_year),
                        match_date=str(match_date),
                        team=home,
                        opponent=away,
                        venue="H",
                        pre_match_mean=home_mean,
                        pre_match_sd=home_sd,
                        pre_match_regime=home_regime,
                    ),
                    BayesianStrengthHistoryPoint(
                        match_id=str(match_id),
                        season_start_year=int(season_start_year),
                        match_date=str(match_date),
                        team=away,
                        opponent=home,
                        venue="A",
                        pre_match_mean=away_mean,
                        pre_match_sd=away_sd,
                        pre_match_regime=away_regime,
                    ),
                ]
            )
            snapshots.append(
                {
                    "home": home,
                    "away": away,
                    "hi": hi,
                    "ai": ai,
                    "goal_diff": float(home_goals - away_goals),
                }
            )

        for snap in snapshots:
            home = str(snap["home"])
            away = str(snap["away"])
            hi = int(snap["hi"])
            ai = int(snap["ai"])
            mean, covariance, _, surprise_z = _kalman_match_update(
                mean,
                covariance,
                home_index=hi,
                away_index=ai,
                observed_goal_diff=float(snap["goal_diff"]),
                home_advantage_goals=home_advantage_goals,
                observation_variance=observation_variance,
            )
            weight = 1.0 - regime_decay
            regime[home] = regime_decay * regime[home] + weight * surprise_z
            regime[away] = regime_decay * regime[away] - weight * surprise_z

        i = j

    final_states = {
        team: (
            float(mean[index]),
            math.sqrt(max(float(covariance[index, index]), 0.0)),
        )
        for team, index in team_index.items()
    }
    return rows, final_states, history, regime


def build_bayesian_strength_rows(
    db_path: Path, **kwargs: float
) -> list[BayesianStrengthRow]:
    return build_bayesian_strength_history(db_path, **kwargs)[0]


def _x_strength(row: BayesianStrengthRow) -> list[float]:
    return [row.expected_goal_diff, row.latent_diff_sd]


def _x_regime(row: BayesianStrengthRow) -> list[float]:
    return [
        row.expected_goal_diff,
        row.latent_diff_sd,
        row.regime_diff,
        abs(row.home_regime) + abs(row.away_regime),
    ]


def _fit_probability_layer(
    rows: list[BayesianStrengthRow],
    *,
    include_regime: bool,
) -> LogisticRegression:
    feature = _x_regime if include_regime else _x_strength
    model = LogisticRegression(
        solver="lbfgs",
        C=1.0,
        max_iter=2000,
        random_state=0,
    )
    model.fit(
        np.asarray([feature(row) for row in rows], dtype=float),
        [row.result for row in rows],
    )
    return model


def _predict_probs(
    model: LogisticRegression,
    row: BayesianStrengthRow,
    *,
    include_regime: bool,
) -> tuple[float, float, float]:
    feature = _x_regime if include_regime else _x_strength
    raw = model.predict_proba(np.asarray([feature(row)], dtype=float))[0]
    mapping = {str(label): float(prob) for label, prob in zip(model.classes_, raw)}
    return tuple(mapping[label] for label in CLASS_ORDER)  # type: ignore[return-value]


def _top_label_ece(
    items: list[tuple[tuple[float, float, float], str]], bins: int = 10
) -> float:
    if not items:
        return 0.0
    total = len(items)
    ece = 0.0
    for lower_index in range(bins):
        lo = lower_index / bins
        hi = (lower_index + 1) / bins
        bucket: list[tuple[float, bool]] = []
        for probs, result in items:
            idx = max(range(3), key=lambda k: probs[k])
            confidence = probs[idx]
            if (lo <= confidence < hi) or (
                lower_index == bins - 1 and confidence == hi
            ):
                bucket.append((confidence, CLASS_ORDER[idx] == result))
        if not bucket:
            continue
        mean_conf = sum(x[0] for x in bucket) / len(bucket)
        accuracy = sum(1.0 for x in bucket if x[1]) / len(bucket)
        ece += (len(bucket) / total) * abs(accuracy - mean_conf)
    return ece


def _metrics(
    items: list[tuple[tuple[float, float, float], str]],
) -> dict[str, float | int | None]:
    if not items:
        return {
            "matches": 0,
            "log_loss": None,
            "brier": None,
            "accuracy": None,
            "top_label_ece": None,
        }
    scores = [score_probabilities(probs, result) for probs, result in items]
    n = len(scores)
    return {
        "matches": n,
        "log_loss": sum(s.log_loss for s in scores) / n,
        "brier": sum(s.brier for s in scores) / n,
        "accuracy": sum(s.correct for s in scores) / n,
        "top_label_ece": _top_label_ece(items),
    }


def _paired_report(
    model_items: list[tuple[tuple[float, float, float], str]],
    market_items: list[tuple[tuple[float, float, float], str]],
) -> dict[str, float | int | None]:
    model_m = _metrics(model_items)
    market_m = _metrics(market_items)
    return {
        "matches": model_m["matches"],
        "model_log_loss": model_m["log_loss"],
        "market_log_loss": market_m["log_loss"],
        "log_loss_delta_model_minus_market": (
            float(model_m["log_loss"]) - float(market_m["log_loss"])
            if model_m["log_loss"] is not None
            and market_m["log_loss"] is not None
            else None
        ),
        "model_brier": model_m["brier"],
        "market_brier": market_m["brier"],
        "brier_delta_model_minus_market": (
            float(model_m["brier"]) - float(market_m["brier"])
            if model_m["brier"] is not None and market_m["brier"] is not None
            else None
        ),
    }


def walk_forward_bayesian_strength(
    db_path: Path,
    *,
    min_train_seasons: int = 3,
) -> dict[str, object]:
    rows, final_states, _, final_regime = build_bayesian_strength_history(db_path)
    seasons = sorted({row.season_start_year for row in rows})
    if len(seasons) <= min_train_seasons:
        raise ValueError("Not enough seasons for walk-forward evaluation")

    strength_all: list[tuple[tuple[float, float, float], str]] = []
    regime_all: list[tuple[tuple[float, float, float], str]] = []
    strength_paired: list[tuple[tuple[float, float, float], str]] = []
    regime_paired: list[tuple[tuple[float, float, float], str]] = []
    market_paired: list[tuple[tuple[float, float, float], str]] = []
    season_reports: list[dict[str, object]] = []

    for test_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[test_index]
        train_seasons = set(seasons[:test_index])
        train = [row for row in rows if row.season_start_year in train_seasons]
        test = [row for row in rows if row.season_start_year == test_season]

        strength_model = _fit_probability_layer(train, include_regime=False)
        regime_model = _fit_probability_layer(train, include_regime=True)

        strength_items = [
            (_predict_probs(strength_model, row, include_regime=False), row.result)
            for row in test
        ]
        regime_items = [
            (_predict_probs(regime_model, row, include_regime=True), row.result)
            for row in test
        ]
        paired_rows = [row for row in test if row.market_probs is not None]
        paired_strength = [
            (_predict_probs(strength_model, row, include_regime=False), row.result)
            for row in paired_rows
        ]
        paired_regime = [
            (_predict_probs(regime_model, row, include_regime=True), row.result)
            for row in paired_rows
        ]
        paired_market = [
            (row.market_probs, row.result)
            for row in paired_rows
            if row.market_probs is not None
        ]

        strength_all.extend(strength_items)
        regime_all.extend(regime_items)
        strength_paired.extend(paired_strength)
        regime_paired.extend(paired_regime)
        market_paired.extend(paired_market)  # type: ignore[arg-type]

        season_reports.append(
            {
                "test_season_start_year": test_season,
                "train_matches": len(train),
                "test_matches": len(test),
                "bayesian_strength": _metrics(strength_items),
                "bayesian_strength_plus_regime": _metrics(regime_items),
                "paired_b365_pre_closing": {
                    "bayesian_strength": _paired_report(
                        paired_strength, paired_market  # type: ignore[arg-type]
                    ),
                    "bayesian_strength_plus_regime": _paired_report(
                        paired_regime, paired_market  # type: ignore[arg-type]
                    ),
                },
            }
        )

    strength_overall = _metrics(strength_all)
    regime_overall = _metrics(regime_all)
    paired_strength_overall = _paired_report(strength_paired, market_paired)
    paired_regime_overall = _paired_report(regime_paired, market_paired)

    final_table = [
        {
            "team": team,
            "mean_strength_goals": state[0],
            "posterior_sd": state[1],
            "regime_surprise": final_regime.get(team, 0.0),
        }
        for team, state in sorted(
            final_states.items(), key=lambda item: (-item[1][0], item[0])
        )
    ]

    return {
        "model": "dynamic_bayesian_strength_v1",
        "state_space_model": (
            "Gaussian latent team strength with random-walk drift; observed goal "
            "difference is home advantage + home strength - away strength + "
            "Gaussian match noise"
        ),
        "parameters": {
            "home_advantage_goals": HOME_ADVANTAGE_GOALS,
            "prior_variance": PRIOR_VARIANCE,
            "observation_variance": OBSERVATION_VARIANCE,
            "process_variance_per_day": PROCESS_VARIANCE_PER_DAY,
            "season_carry": SEASON_CARRY,
            "season_reset_variance": SEASON_RESET_VARIANCE,
            "regime_decay": REGIME_DECAY,
        },
        "hyperparameter_policy": (
            "v1 state parameters fixed before OOS evaluation; no OOS tuning"
        ),
        "same_day_policy": (
            "all pre-match states for a date are frozen before any result from "
            "that date updates the posterior"
        ),
        "promotion_policy": (
            "new/promoted teams enter at neutral mean 0 with prior variance 1; "
            "no invented lower-league strength"
        ),
        "probability_layer": (
            "multinomial logistic calibration fit only on earlier seasons; strength "
            "model uses pre-match expected goal difference and posterior uncertainty"
        ),
        "regime_policy": (
            "candidate-only extension using pre-match exponentially weighted signed "
            "standardized goal-difference surprises; current-match surprise never "
            "enters its own prediction"
        ),
        "split_policy": (
            "walk-forward by season; each held-out season uses calibration trained "
            "only on earlier seasons"
        ),
        "bayesian_strength": {
            "overall_model": strength_overall,
            "paired_overall": paired_strength_overall,
        },
        "bayesian_strength_plus_regime": {
            "overall_model": regime_overall,
            "paired_overall": paired_regime_overall,
        },
        "final_strengths": final_table,
        "seasons": season_reports,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Leakage-safe walk-forward dynamic Bayesian EPL team-strength audit."
    )
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/football1.sqlite")
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-train-seasons", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = walk_forward_bayesian_strength(
        args.database, min_train_seasons=args.min_train_seasons
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote Bayesian strength report to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
