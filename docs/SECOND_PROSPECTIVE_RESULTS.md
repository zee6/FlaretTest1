# Football 1 — Second Prospective Results

**Batch:** 12–14 September 2026 EPL slate  
**Predictions locked:** 4 September 2026 snapshot  
**Settlement status:** 10/10 complete  
**Decision weight:** unchanged at zero for experimental lanes

## Executive summary

The second untouched ten-match batch produced a mixed but informative result.

1. The live market consensus again beat the original Football 1 probability model on both log loss and Brier score.
2. The pre-frozen 15-day general-recency shadow substantially improved on original Football 1 and the 30-day shadow, and came very close to the market on log loss, but still did not beat the market.
3. The first batch's draw-calibration problem repeated more strongly: all four realized draws received lower probability from original Football 1 than from the locked market.
4. Draw Possibility's No. 1 ranked match, Bournemouth–Brentford, finished 2–2. The top two frozen candidates contained one draw. However, across the full ten-match slate the Draw Possibility ranking AUC was worse than the market's pDraw ranking because two additional draws occurred in matches ranked 9th and 10th by Draw Possibility.
5. The official research portfolio still placed zero compulsory bets and therefore preserved starting capital. Descriptive shadow portfolios remained negative.

Nothing in this batch activates a probability weight, draw override, betting threshold, stake rule or product recommendation.

## Results

Final scores:

- Crystal Palace 2–3 Ipswich Town
- Chelsea 2–2 Hull City
- Liverpool 0–0 Fulham
- Aston Villa 1–2 Nottingham Forest
- AFC Bournemouth 2–2 Brentford
- Tottenham Hotspur 0–0 Everton
- Sunderland 0–2 Arsenal
- Coventry City 0–5 Brighton & Hove Albion
- Manchester United 0–1 Manchester City
- Leeds United 4–1 Newcastle United

Outcome counts:

- Home wins: 1
- Draws: 4
- Away wins: 5

## Primary probability test

Second batch only:

| Model | Log loss | Brier | H/D/A argmax accuracy |
|---|---:|---:|---:|
| Market consensus | **1.183617** | **0.738399** | 40% |
| Original Football 1 | 1.196342 | 0.747112 | 40% |

Football 1 minus market:

- log loss: **+0.012725** worse
- Brier: **+0.008712** worse

Across all 20 prospectively settled matches:

| Model | Mean log loss | Mean Brier |
|---|---:|---:|
| Market consensus | **1.113616** | **0.685876** |
| Original Football 1 | 1.122591 | 0.692334 |

Combined Football 1 minus market:

- log loss: **+0.008975** worse
- Brier: **+0.006458** worse

The prospective evidence therefore continues to agree with the historical result: the retained fixed residual has not shown that it improves the market probability anchor.

## General recency — untouched 10-match comparison

The 30-day and 15-day shadows were frozen before these outcomes and scored on exactly the same ten fixtures.

| Model | Log loss | Brier | Argmax accuracy |
|---|---:|---:|---:|
| Market consensus | **1.183617** | **0.738399** | 40% |
| 15-day recency | 1.183953 | 0.739611 | 40% |
| 30-day recency | 1.187802 | 0.742361 | 40% |
| Original equal-weight Football 1 | 1.196342 | 0.747112 | 40% |

Delta versus market:

- 15-day: log loss **+0.000336**, Brier **+0.001212**
- 30-day: log loss **+0.004186**, Brier **+0.003962**
- original: log loss **+0.012725**, Brier **+0.008712**

Interpretation:

- 15 days clearly beat the original and 30-day Football 1 variants on this untouched batch.
- 15 days did **not** beat the market.
- Accuracy was identical for every model, so the improvement is probability quality/calibration rather than additional H/D/A winners.
- One ten-match batch is not enough to activate 15-day recency or replace the original model.
- The correct next step is additional unchanged prospective accumulation, not another historical half-life search.

## Draw calibration error — repeated prospectively

First batch:

- realized draws: 6
- Football 1 moved Draw probability above market on 1
- Football 1 moved Draw probability below market on 5
- mean realized-Draw probability move: **−0.365pp**
- mean Draw log-loss damage versus market: **+0.013553**

Second untouched batch:

- realized draws: 4
- Football 1 moved Draw probability above market on **0**
- Football 1 moved Draw probability below market on **4**
- mean realized-Draw probability move: **−0.863pp**
- mean Draw log-loss damage versus market: **+0.038220**
- mean Draw Brier damage versus market: **+0.024314**

Across the two batches, the same directional problem has now appeared twice: original Football 1 frequently removes probability from Draw on matches that subsequently draw.

This is a meaningful diagnostic, but it is **not** permission to paste an arbitrary Draw boost onto the model. It strengthens the case for continued draw-specific research and for keeping Draw Possibility separate from calibrated probability until an actual probability correction is prospectively justified.

## Draw Possibility — first untouched prospective slate

Frozen top two before kickoff:

1. AFC Bournemouth v Brentford — internal balance rank 99.21/100
2. Leeds United v Newcastle United — internal balance rank 95.02/100

Results:

- Bournemouth 2–2 Brentford — **Draw**
- Leeds 4–1 Newcastle — Home win

Predeclared summaries:

- top 1: 1/1 draw
- top 2: 1/2 draws
- fixed ≤2pp balance flag: 1/1 draw
- fixed ≤5pp flag: 1/2 draws
- fixed ≤10pp flag: 1/2 draws

Gross research-price result for the top two / ≤5pp / ≤10pp class:

- +1.8 units over two £1-equivalent stakes
- +90% research-price ROI

This must **not** be presented as validated betting performance. It is two observations and the original best-price locks did not preserve bookmaker provenance for every quote.

More importantly, the complete-slate ranking result was not strong:

- Draw Possibility AUC: **0.4167**
- market pDraw AUC: **0.4583**
- delta: **−0.0417**

Why? Two additional draws occurred in highly unbalanced matches:

- Liverpool 0–0 Fulham — Draw Possibility rank 9
- Chelsea 2–2 Hull — Draw Possibility rank 10

Therefore the correct interpretation is:

> The extreme-balance top candidate produced an encouraging prospective hit, but Draw Possibility did not rank all four draws well across this slate.

Preserve the score definition and accumulate additional prospective slates. Do not alter it to capture the two low-ranked draws after seeing them.

## Portfolio observer

Official research portfolio:

- starting bankroll: 1000
- compulsory bets: **0**
- final bankroll: **1000**
- drawdown: **0**

This remains the only non-hindsight policy because Football 1 still has no prospectively validated betting selection rule.

Descriptive shadow portfolios after all 20 settled matches:

### Result call + positive price interest

Seven selections, two wins.

Flat 1% starting-bankroll stake:

- final bankroll: **963.20**
- P&L: **−36.80**
- max drawdown: **4.23%**
- turnover ROI: **−52.57%**

Drawdown throttle:

- final bankroll: **966.57**
- P&L: **−33.43**
- max drawdown: **3.89%**

Previous-week-loss throttle:

- final bankroll: **973.34**
- P&L: **−26.66**
- max drawdown: **3.22%**

### Raw max-EV outcome every settled match

Twenty selections, four wins.

Flat stake:

- final bankroll: **912.70**
- P&L: **−87.30**
- max drawdown: **9.25%**

Drawdown throttle:

- final bankroll: **927.95**
- P&L: **−72.05**
- max drawdown: **7.73%**

Again, risk controls reduced damage. They did not create edge.

## Governance after this batch

No activation follows.

Specifically:

- do not increase Draw probability by fiat;
- do not replace original Football 1 with 15-day recency yet;
- do not promote Draw Possibility from one top-ranked hit;
- do not choose a new balance threshold after seeing the two low-ranked draws;
- do not infer that raw EV is validated;
- do not change portfolio exposure because of one good or bad matchweek.

The next legitimate step is unchanged prospective accumulation using the already-defined lanes.

## Reproducibility

Evaluation workflow:

- workflow: EPL Prospective Weekend Evaluation
- run: 34937754871
- artifact: epl-prospective-weekend-evaluation-2026-09-12-14
- artifact ID: 10384351689
- artifact ZIP digest: sha256:8405d5908b76d909e8a8662885e7c908742628fb339e3aa2bab94bdb3b482cd6

The artifact contains:

- primary probability report
- 15d/30d recency report
- Draw Possibility report
- prospective error anatomy
- frozen two-batch error comparison
- prospective Portfolio report
- evidence register
