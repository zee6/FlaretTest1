# Football 1 — First Prospective Settlement Results

**Settlement date:** 9 September 2026  
**Prediction lock:** 4 September 2026 09:20:03 UTC  
**Status:** first genuinely forward settlement batch; tiny sample; no tuning permitted

## Scope

The original Football 1 prospective lock contained 20 EPL fixtures. The first 10 fixtures, played 4–6 September 2026, have now completed and were settled as one batch. The remaining 10 fixtures scheduled for 12–14 September remain untouched.

Each settlement references the immutable original prediction record and content hash. Results were verified against official Premier League Matchweek 3 reports and cross-checked against a structured soccer results feed before settlement.

Official result sources used:

- Ipswich Town 0–2 Liverpool: https://www.premierleague.com/en/news/4712665
- Saturday 5 September matchweek report: https://www.premierleague.com/en/news/4706437/saturday-wrap-man-city-extend-winning-start-as-palace-claim-first-win
- Sunday 6 September matchweek report: https://www.premierleague.com/en/news/4706438/sunday-wrap-arsenal-pass-big-early-test-after-late-drama-at-everton/

## Results

| Fixture | Result |
|---|---:|
| Ipswich Town v Liverpool | 0–2 |
| Newcastle United v Bournemouth | 2–2 |
| Brentford v Sunderland | 1–1 |
| Brighton & Hove Albion v Leeds United | 1–1 |
| Manchester City v Coventry City | 1–0 |
| Fulham v Crystal Palace | 2–3 |
| Nottingham Forest v Tottenham Hotspur | 0–0 |
| Hull City v Aston Villa | 0–0 |
| Everton v Manchester United | 2–2 |
| Arsenal v Chelsea | 2–1 |

Six of the ten matches were draws. This is an extreme one-week outcome and must not be used to recalibrate draw probabilities or choose a draw strategy after the fact.

## Proper probability scoring

Lower is better.

| Metric | Market consensus | Football 1 | Football 1 minus market |
|---|---:|---:|---:|
| Mean log loss | **1.043615** | 1.048840 | +0.005224 |
| Mean Brier | **0.633353** | 0.637557 | +0.004204 |

The market benchmark therefore wins the first 10-match prospective probability comparison by a small amount on both proper scoring rules.

The de-vigged market and Football 1 had the same H/D/A argmax on all 10 matches, and each argmax was correct in 3/10. Accuracy is secondary; the proper scores above are the primary probability comparison.

## Draw observation

Actual draw rate in this batch: **60% (6/10)**.

Mean pre-match draw probability across all 10 fixtures:

- market: **24.287%**,
- Football 1: **23.605%**.

On the six matches that actually drew, Football 1 reduced the market draw probability in five and increased it in only one. This tiny sample is not enough to infer a stable draw effect, but it certainly does not justify overriding the earlier negative draw-hybrid and draw-residual findings.

Do **not** increase draw weight or tune a draw rule from this week.

## Fixed threshold sensitivity panel

These rows were pre-existing reporting thresholds and are **not betting strategies selected from this prospective result**.

| Recorded max-EV threshold | Settled qualifying records | P&L units | ROI |
|---:|---:|---:|---:|
| 2.5% | 7 | -5.25 | -75.0% |
| 5.0% | 6 | -6.00 | -100.0% |
| 7.5% | 1 | -1.00 | -100.0% |
| 10.0% | 1 | -1.00 | -100.0% |

The single 7.5%/10% observation was Manchester City v Coventry City, where the model's raw max-EV outcome was the very long-priced Coventry away win even though Manchester City remained overwhelmingly the most likely result. Coventry lost 1–0.

This is a concrete forward example of the pathology already identified historically: long odds can amplify a very small model-market probability disagreement into a visually large raw EV number. It reinforces the separation between model disagreement, quote premium and genuine confidence.

## Interpretation

The first forward evidence is negative for the retained fixed-market residual:

- it did not beat the market on log loss,
- it did not beat the market on Brier,
- the fixed threshold sensitivity rows were poor,
- and a draw-heavy week exposed no evidence that the current residual was usefully increasing draw probabilities.

This is useful evidence, not a reason to alter the model after ten matches.

The correct action is to preserve the result and continue the untouched prospective test.

## Governance

- No model weight changes from this batch.
- No threshold selection from this batch.
- No draw-probability adjustment from this batch.
- No staking-rule promotion from this batch.
- The 12–14 September predictions remain immutable and unsettled.
- Future prospective batches should be appended and judged cumulatively rather than replacing or averaging away this result.
