# Football 1 — Result Call + Price Audit

Status date: 7 September 2026  
Status: completed historical diagnostic; preferred product class remains unvalidated  
Decision weight: 0.0  
Promotion allowed: false

This document records the first explicit audit of the product class David identified as most desirable:

> Football 1's most likely H/D/A result is itself available at a price that appears favourable to Football 1.

It is additive to `PHASE1C_RESULTS.md`, `PROJECT_STATE.md`, `PROSPECTIVE_PROTOCOL.md`, `HYBRID_OPPORTUNITY.md`, and `RESIDUAL_MAGNITUDE_AUDIT.md`.

## Question

Football 1 must distinguish at least two kinds of candidate:

1. **Result Call + Price** — the result Football 1 makes most likely is also favourably priced according to Football 1. This is the preferred or “gold-standard” structural class.
2. **Alternative Price Interest** — a different H/D/A outcome has the highest apparent price discrepancy even though it is not Football 1's result call.

This audit asked whether the preferred class historically behaved better than the alternative-price class, without choosing a tuned minimum edge or staking rule.

## Experimental design

Implementation: `src/football1/result_price_audit.py`

Model under audit:

- `fixed_market_offset_football_slant_v1`;
- alpha fixed at `0.10`;
- historical probability anchor: de-vigged Bet365 pre-closing H/D/A probabilities;
- quoted Bet365 pre-closing odds used for the raw price test.

Validation:

- chronological walk-forward by season;
- each test season fitted only on earlier seasons;
- 4,200 OOS matches;
- frozen 4 September 2026 canonical database;
- no edge threshold search;
- no staking optimisation.

Raw positive EV means only:

`model probability × quoted decimal odds - 1 > 0`.

Zero is mathematical break-even, **not** a validated recommendation threshold.

The historical seasons had already been inspected elsewhere in Football 1, so these results are diagnostic rather than fresh confirmation.

## Overall result-call accuracy

Across the 4,200 OOS matches, Football 1's H/D/A argmax was correct **54.64%** of the time.

Accuracy is reported only as descriptive context and is not the primary calibration metric.

## Preferred class — Result Call + raw favourable price

Definition:

- Football 1 H/D/A argmax;
- the same outcome has raw model EV above zero at the quoted Bet365 price.

Results:

- matches: **1,299**;
- wins: **651**;
- hit rate: **50.12%**;
- mean quoted odds: **2.064**;
- mean market probability: **50.05%**;
- mean Football 1 probability: **53.82%**;
- mean Football 1 edge versus market: **+3.77 percentage points**;
- mean total probability edge versus quoted break-even: **+1.83 percentage points**;
- mean raw model EV: **+3.91%**;
- observed rate minus market probability: **+0.06 percentage points**;
- observed rate minus Football 1 probability: **-3.70 percentage points**;
- flat one-unit P&L: **-47.96 units**;
- ROI: **-3.69%**;
- maximum drawdown: **61.55 units**.

### Interpretation

The market was essentially perfectly calibrated in this class:

- market expectation: **50.05%**;
- observed wins: **50.12%**.

Football 1 raised the same set of outcomes to an average **53.82%**, creating the appearance of value, but the observed rate did not move with it.

The core problem was therefore **overconfidence in the residual correction**, not merely candidate selection.

## Narrower preferred class — result call is also the best H/D/A price discrepancy

Definition:

- Football 1 result call has raw positive EV;
- that same result is also the highest-EV H/D/A outcome for the match.

Results:

- matches: **849**;
- hit rate: **52.53%**;
- mean odds: **1.981**;
- mean market probability: **52.87%**;
- mean Football 1 probability: **55.71%**;
- mean raw model EV: **+3.37%**;
- observed minus market expectation: **-0.34 percentage points**;
- observed minus Football 1 expectation: **-3.19 percentage points**;
- P&L: **-22.49 units**;
- ROI: **-2.65%**;
- maximum drawdown: **33.07 units**.

This was the least-bad price-interest class in the audit, but it still did not beat the bookmaker historically and therefore earns no promotion.

## Alternative-price class

Definition:

- at least one H/D/A outcome has raw positive model EV;
- the highest-EV outcome is **different** from Football 1's result call.

Results:

- matches: **1,806**;
- hit rate: **20.49%**;
- mean odds: **5.12**;
- mean market probability: **17.99%**;
- mean Football 1 probability: **20.39%**;
- mean raw model EV: **+10.18%**;
- observed minus Football 1 probability: approximately **+0.10 percentage points**;
- observed minus market probability: approximately **+2.50 percentage points**;
- P&L: **-118.75 units**;
- ROI: **-6.58%**;
- maximum drawdown: **147.93 units**.

This class is a strong warning against reading raw EV as conviction. Its quoted odds were much longer and raw model EV looked much larger, yet the economic result was substantially worse.

## Any raw positive-price interest

If the highest-EV H/D/A outcome was used whenever at least one outcome had raw positive model EV:

- matches: **2,655**;
- hit rate: **30.73%**;
- mean odds: **4.116**;
- mean Football 1 probability: **31.68%**;
- mean raw model EV: **+8.00%**;
- P&L: **-125.66 units**;
- ROI: **-4.73%**.

There were **1,545** matches with no H/D/A outcome above raw mathematical break-even.

## Result-call + price by outcome

Within the 1,299 preferred-class observations:

- Home: **1,170** cases, ROI approximately **-0.14%**;
- Draw: **6** cases, ROI approximately **+3.33%** — far too small for inference;
- Away: **123** cases, ROI approximately **-6.87%**.

The Home subset being near break-even is interesting descriptively, but it was observed after the fact and must not be converted into a Home-only rule.

## Relationship to the residual-magnitude audit

The companion residual-magnitude audit found that larger Football 1 deviations from the market became **worse**, not more reliable.

This result+price audit is consistent with that finding. Even in the structurally attractive class where Football 1's preferred result also appears favourably priced, the market expectation was essentially correct while Football 1 was too optimistic.

Therefore:

- `result_call + price` is a useful **product category**;
- it is not yet a validated **betting category**;
- residual magnitude must not be treated as confidence;
- raw EV must remain separate from model disagreement and bookmaker quote generosity.

## Product implication

Football 1 should retain the distinction between:

- **Result Call** — which H/D/A outcome is most likely;
- **Result + Price** — the same outcome also appears cheap;
- **Alternative Price** — a different H/D/A outcome appears mispriced;
- **Quote Premium** — the bookmaker's selected price is generous versus market consensus;
- **Model Disagreement** — Football 1 differs from the market probability.

The preferred interface can eventually give Result + Price special prominence because it is the conceptually strongest transaction class, but the label must remain descriptive until an untouched prospective rule earns promotion.

A candidate should never be called `HIGH CONFIDENCE`, `BET`, or equivalent merely because the result call and raw positive EV coincide.

## Decision

1. Preserve Result Call + Price as the preferred candidate **class**.
2. Do not promote it to a betting rule.
3. Do not select a minimum edge from this historical sample.
4. Keep Football 1 probability disagreement separate from bookmaker quote premium.
5. Treat the residual model's fair-probability correction as unvalidated/overconfident overall.
6. Continue prospective evidence collection at zero decision weight.
7. Investigate movement/closing-price information separately: a signal may conceivably be useful for price timing even if it is not a superior fair-probability estimate.
