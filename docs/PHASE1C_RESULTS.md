# Phase 1C Results — EPL historical audit and first market-slant tests

Date: 2026-09-04

## Status

Phase 1C is complete. The pipeline was executed from source in GitHub Actions and all reported figures below were regenerated from downloaded Football-Data.co.uk EPL files rather than a hand-carried local database.

## Data integrity

- Seasons: 2012/13 through 2026/27
- Source files: 15
- Completed matches: 5,340
- Canonical SQLite matches: 5,340
- Row reconciliation: exact
- Schema union: 203 columns
- Schema intersection: 29 columns
- Unclassified columns after schema review: 0
- Current 2026/27 sample at run time: 20 completed matches
- Bet365 pre-closing H/D/A odds coverage: 100% across all 5,340 matches

Historical and current odds are kept distinct by timing class. Pinnacle is flagged for 2025/26 onward because Football-Data warns that its feed may be stale from 2025-07-23 onward.

## Fixed market benchmark

De-vigged Bet365 pre-closing 1X2 probabilities across all 5,340 matches:

- Log loss: 0.959205
- Multiclass Brier score: 0.567947
- Accuracy: 55.04%
- Mean quoted overround: 4.22%

This is the principal market hurdle.

## Football-only walk-forward model

Specification:

- multinomial logistic regression
- no bookmaker odds in model features
- model fit only on seasons strictly earlier than each OOS season
- all fixtures on a calendar date are snapshotted before any result on that date updates team state
- football features include lagged Elo, short/medium form, goals, shots, shots on target, rest and history depth

Across 4,200 OOS matches:

- Football-only log loss: 0.979445
- Paired Bet365 log loss: 0.960279
- Delta: +0.019166 (football-only model worse)
- Football-only Brier: 0.580840
- Paired Bet365 Brier: 0.569005
- Delta: +0.011835 (football-only model worse)

The football-only model lost to Bet365 in every held-out season. This negative result is retained.

## Market-conditioned slant v1

A market-only calibration control and a market-plus-football model were both fit using only earlier seasons.

Across 4,200 OOS matches:

- Raw Bet365 log loss: 0.960279
- Market-only recalibration: 0.962042
- Market + football: 0.970268

The unconstrained slant degraded the market benchmark.

## Fixed-market residual slant

The architecture was tightened so the de-vigged Bet365 probabilities remain an immutable offset. Football features can only learn residual H-vs-D and A-vs-D logit adjustments. Zero residual adjustment reproduces the market exactly; this invariant is unit-tested.

Regularization alpha = 0.10 was fixed before this specification's OOS evaluation.

Across 4,200 OOS matches:

- Raw Bet365 log loss: 0.960279
- Offset calibration log loss: 0.960811
- Offset football slant log loss: 0.962730
- Offset football delta vs raw: +0.002451
- Raw Bet365 Brier: 0.569005
- Offset football Brier: 0.570342
- Brier delta vs raw: +0.001337

The residual architecture is much safer than the unconstrained slant, but it still does not beat the market overall.

## Fixed-threshold exploratory mispricing tail test

This test uses the already-fixed offset model (alpha = 0.10). For every OOS match, at most one outcome is eligible: the outcome with maximum model expected value using the quoted Bet365 decimal odds. A flat one-unit stake is made when model EV meets the threshold.

The threshold grid was declared as a sensitivity grid and all thresholds are reported. No single threshold may be selected as a validated winner from these same OOS results.

| Minimum model EV | Bets | Mean predicted EV | P&L (units) | ROI | Max drawdown |
|---:|---:|---:|---:|---:|---:|
| 2.5% | 1,616 | 7.64% | -64.23 | -3.97% | 120.18 |
| 5.0% | 987 | 10.21% | -8.38 | -0.85% | 66.46 |
| 7.5% | 580 | 13.07% | +23.52 | +4.06% | 57.12 |
| 10.0% | 366 | 15.65% | +11.88 | +3.25% | 42.15 |

The positive 7.5% and 10% historical tails are exploratory only. Reasons not to claim an edge:

1. The broad probability model still loses to the market.
2. Multiple thresholds are displayed and the profitable thresholds are observed ex post.
3. Realized returns are far below the model's predicted EV, indicating residual overconfidence/miscalibration.
4. Returns are unstable across seasons.
5. Recent 2025/26 tail performance is poor.

## Decision

Do not tune alpha or choose a historical threshold using these OOS results.

Retain the fixed-market residual architecture because it provides a safe zero-adjustment fallback and because the extreme-disagreement tail is worth further investigation. The next phase should add genuinely time-available football information and establish a prospective validation protocol before claiming a tradeable edge.
