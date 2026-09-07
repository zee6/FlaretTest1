# Football 1 — Residual Magnitude Audit

Status date: 7 September 2026  
Status: completed historical diagnostic; negative for using disagreement magnitude as confidence  
Decision weight: 0.0  
Promotion allowed: false

This document records the first explicit audit of whether larger Football 1 deviations from the bookmaker market historically became more reliable.

It is additive to `PHASE1C_RESULTS.md`, `PROJECT_STATE.md`, `PROSPECTIVE_PROTOCOL.md`, and `HYBRID_OPPORTUNITY.md`.

## Question

Football 1 increasingly separates:

- the market benchmark;
- Football 1's probability estimate;
- bookmaker quote generosity;
- total price discrepancy.

That creates a natural temptation to treat a larger Football 1 probability residual versus the market as stronger model conviction.

This audit asked a narrower question before allowing that interpretation:

> When the existing fixed-market residual model historically moved farther away from the de-vigged market, did those larger deviations actually become more trustworthy?

The answer was **no**.

## Experimental design

Implementation: `src/football1/residual_magnitude_audit.py`

Model under audit:

- `fixed_market_offset_football_slant_v1`;
- alpha fixed at `0.10`;
- historical anchor: de-vigged Bet365 pre-closing H/D/A probabilities.

Validation:

- chronological walk-forward by season;
- each test season fitted only on earlier seasons;
- 4,200 OOS matches;
- frozen 4 September 2026 canonical database;
- frozen database SHA-256: `4b5c751b22608026fb18eb190279c13b41d50ab88055057787c041ae4b841454`.

The audit did **not** search for or select a threshold. Historical seasons had already been inspected elsewhere in Football 1, so these results are diagnostic rather than fresh confirmation.

## Overall result

Across all 4,200 OOS matches:

| Metric | Market | Football 1 residual | Football 1 minus market |
|---|---:|---:|---:|
| Multiclass Brier | 0.569005 | 0.570342 | +0.001337 (worse) |
| Multiclass log loss | 0.960279 | 0.962730 | +0.002451 (worse) |

Mean maximum absolute H/D/A probability residual was about **2.61 percentage points**.

## Residual-size reference distribution

Maximum absolute H/D/A residual per match:

| Percentile | Absolute residual |
|---|---:|
| 50th | 2.30 pp |
| 75th | 3.40 pp |
| 90th | 4.63 pp |
| 95th | 5.55 pp |
| 99th | 7.77 pp |
| Maximum | 16.71 pp |

Largest positive shift toward one H/D/A outcome:

| Percentile | Positive shift |
|---|---:|
| 50th | 2.09 pp |
| 75th | 3.18 pp |
| 90th | 4.43 pp |
| 95th | 5.37 pp |
| 99th | 7.75 pp |
| Maximum | 15.43 pp |

These percentiles describe historical unusualness only. They are **not confidence levels** and are not operational thresholds.

## Larger residuals did not improve

Matches were split into five equal groups by maximum absolute residual magnitude.

| Residual quintile | Matches | Mean max residual | Brier delta vs market | Log-loss delta vs market |
|---|---:|---:|---:|---:|
| 1 — smallest | 840 | 0.84 pp | +0.000113 | +0.000170 |
| 2 | 840 | 1.64 pp | +0.001511 | +0.002910 |
| 3 | 840 | 2.31 pp | +0.000457 | +0.000931 |
| 4 | 840 | 3.15 pp | +0.002027 | +0.003274 |
| 5 — largest | 840 | 5.10 pp | +0.002576 | +0.004970 |

Every quintile was worse than the market. The largest-disagreement quintile was the worst group on both Brier and log loss.

There is therefore no historical basis for saying:

> larger Football 1 disagreement = higher confidence.

## Largest positive model shift also became worse

For each match, the audit selected whichever H/D/A outcome Football 1 increased most relative to the market, then ranked those upward shifts into quintiles.

| Shift quintile | Matches | Mean shift | Market p | Model p | Actual rate | Brier delta | Log-loss delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 840 | 0.70 pp | 36.97% | 37.67% | 34.88% | +0.000290 | +0.000733 |
| 2 | 840 | 1.42 pp | 41.40% | 42.81% | 42.62% | -0.000094 | -0.000041 |
| 3 | 840 | 2.08 pp | 42.81% | 44.89% | 42.62% | +0.000459 | +0.000923 |
| 4 | 840 | 2.93 pp | 45.42% | 48.35% | 45.12% | +0.001038 | +0.002063 |
| 5 — largest | 840 | 4.89 pp | 46.04% | 50.94% | 46.07% | +0.002234 | +0.006159 |

The second quintile was essentially flat/slightly better, but there is no monotonic improvement. The highest-shift group was materially worse: the market expectation was about 46.04%, Football 1 raised it to 50.94%, while the observed rate was only 46.07%.

## Draw-specific finding

Draw was the outcome receiving the largest upward residual on 291 OOS matches.

For those matches:

- mean market draw probability: **25.16%**;
- mean Football 1 draw probability: **26.83%**;
- mean upward shift: **+1.67 percentage points**;
- actual draw rate: **23.02%**;
- Brier delta versus market: **+0.000545** (worse);
- log-loss delta versus market: **+0.001572** (worse).

This matters for the Draw Profile product discussion. Football 1 should make draw-like matches visible and rank them as a separate match-shape question, but the retained residual model has not earned permission to inflate draw probability or draw confidence.

## Home and Away shifts

The same broad conclusion holds when the largest upward shift was toward Home or Away:

- Home-shift cases: 2,118 matches; Brier +0.000536, log loss +0.001661 versus market.
- Away-shift cases: 1,791 matches; Brier +0.001120, log loss +0.002394 versus market.

Neither class earned predictive promotion.

## Seasonal stability

The residual model beat the market slightly in a few individual seasons, including 2018, 2022 and 2023 start years, but lost in most seasons and degraded particularly strongly in the latest observed 2026 sample.

This instability is further reason not to infer confidence from residual magnitude.

## Decision

1. **Do not use residual magnitude as confidence.**
2. **Do not choose a residual threshold from these historical results.**
3. Keep `model disagreement versus market` as a descriptive component of edge anatomy.
4. Keep bookmaker quote premium separate from model disagreement.
5. Raw EV remains a separate odds-scaled diagnostic and must not masquerade as model conviction.
6. Draw Profile remains a visibility/ranking concept, not a licence to boost draw probability.
7. Any future rule that acts on residual magnitude must be frozen before prospective testing and begin at zero decision weight.

## Product implication

A future interface may legitimately say:

- Football 1 differs from market by X percentage points;
- this is historically an unusual or ordinary-sized disagreement;

but it must **not** turn that magnitude into labels such as `HIGH CONFIDENCE` without new evidence.

The product should prefer transparent language such as **model disagreement** over language that implies unearned certainty.
