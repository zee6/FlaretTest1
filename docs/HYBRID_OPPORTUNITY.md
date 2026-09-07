# Football 1 — Hybrid Opportunity Layer

Status date: 7 September 2026  
Status: implemented research layer; decision weight zero; interface deferred

This document records the under-the-hood design agreed after the draw-jury audit. It is additive to `PROJECT_STATE.md`, `PHASE1C_RESULTS.md`, and `PROSPECTIVE_PROTOCOL.md`.

## Governing distinction

Football 1 must answer several different questions without conflating them:

1. **Result Call / Prophet** — which H/D/A outcome is individually most likely?
2. **Best Price / Trader** — which H/D/A quoted price differs most favourably from Football 1's fair-price estimate?
3. **Result + Price** — is the most likely result itself also favourably priced? This is the preferred class of candidate, but no minimum discrepancy has yet earned promotion.
4. **Draw Profile** — is the fixture unusually draw-like relative to other matches and to the normal EPL draw environment, even if Draw is not the H/D/A argmax?
5. **Non-Loss / Favourite Vulnerability** — what is the probability that a side avoids defeat (`1X` or `X2`), and how does its fair price compare with the cost of covering both component outcomes?

A lower raw probability must not make Draw invisible. A draw can be the strongest draw candidate in a slate without being the single most likely H/D/A result.

## Implemented opportunity layer

`src/football1/opportunity_layer.py` is a read-only derived observer over immutable prospective prediction records.

It calculates independently for Home, Draw and Away:

- Football 1 probability;
- margin-free market probability;
- probability difference versus market;
- Football 1 fair decimal odds;
- available best decimal odds;
- quoted break-even probability;
- raw model-implied EV at the available price.

It then records separately:

- `result_call`;
- `best_price_outcome`;
- `result_plus_price_raw_interest`;
- all outcomes with raw positive model EV.

Raw positive EV is **not** a betting recommendation. `betting_threshold` and `stake_rule` remain `null`, and `decision_weight` remains `0.0`.

## Slate-relative rankings

`src/football1/slate_rankings.py` ranks distinct research views across the currently available locked fixture slate without manufacturing a betting recommendation.

It exposes separate slate champions for:

- strongest result call;
- strongest result + price raw interest, when one exists;
- best pure price discrepancy;
- highest draw probability;
- highest draw uplift versus market;
- most balanced Home/Away match shape;
- strongest outsider non-loss proposition.

A category can always have a highest-ranked fixture even when the difference is too small to be actionable. The output therefore remains a **ranking observer**, not a recommendation engine.

## Non-loss analysis

The same layer treats the two double-chance propositions as genuine binary events:

- `1X = Home + Draw`;
- `X2 = Draw + Away`.

The probabilities are exact sums because the component outcomes are mutually exclusive.

Until an actual bookmaker double-chance quote is ingested, Football 1 also calculates the effective price of covering the two component outcomes by dutching the separately available H/D/A prices. This explicitly includes the cost of buying two outcomes rather than pretending the combined event inherits a frictionless fair price.

The market outsider is identified from the margin-free Home/Away market probabilities, and the corresponding outsider-or-draw proposition is exposed as `outsider_non_loss`.

No staking rule or threshold is attached.

`src/football1/double_chance_odds.py` adds an **optional** event-level collector for the provider's real `double_chance` market. It requires explicit event selection (`--event-id` or `--max-events`) so routine 1X2 refreshes cannot silently spend additional API quota. The synthetic dutch calculation remains useful as a friction benchmark even after real double-chance quotes are available.

## Draw Profile research observer

`src/football1/draw_profile.py` implements a transparent hybrid observer with a nested chronological audit.

Its candidate inputs are deliberately interpretable:

- market draw probability;
- retained fixed-RF draw probability;
- RF draw residual versus market;
- market Home/Away balance;
- retained-RF Home/Away balance;
- independent-Poisson draw probability;
- Dixon-Coles draw probability;
- Davidson draw probability;
- bivariate-Poisson draw probability;
- gamma-frailty draw probability;
- football-jury mean draw probability;
- football-jury draw disagreement/spread;
- expected-goal gap;
- expected total goals;
- independent-Poisson mass on 0-0, 1-1 and 2-2;
- absolute pre-match Elo difference.

The hybrid is a regularized logistic observer, not a hand-built confidence score. Base juror probabilities are first produced out of sample by season. The hybrid then trains only on **earlier base-OOS seasons** and scores a later season. This second chronological boundary prevents a stacker from being trained on the same matches it evaluates.

Because the hybrid was designed after existing Football 1 historical research had already been inspected, its historical results remain exploratory. It cannot be treated as fresh confirmation, regardless of whether it beats the market in the current audit.

### First nested historical result — NEGATIVE versus market

The first full nested audit completed successfully on the frozen 4 September canonical database.

Common nested OOS sample:

- 3,440 matches;
- 803 draws;
- observed draw rate: 23.34%;
- hybrid test seasons: 2017 through 2026 start years.

Draw Profile v1 versus the market control:

| Metric | Hybrid Draw Profile v1 | Market | Hybrid minus market |
|---|---:|---:|---:|
| Draw Brier | 0.177702 | 0.176301 | +0.001402 (worse) |
| Draw log loss | 0.539168 | 0.535305 | +0.003863 (worse) |
| Draw AUC | 0.575014 | 0.580036 | -0.005022 (worse) |
| Calibration ECE | 0.027054 | 0.009220 | +0.017834 (worse) |
| Top-20% observed draw rate | 28.05% | 29.36% | -1.31 percentage points |

The market's top draw quintile therefore remained more useful than the hybrid's top quintile. The hybrid's highest quintile also overpredicted draws materially: mean predicted draw probability about 34.80% versus an observed 28.05%.

**Decision:** Draw Profile v1 receives no probability weight and must not alter Football 1 fair odds. Its components may still be useful descriptively for identifying match shape and for forming future hypotheses, but the v1 blend did not earn predictive promotion.

### Non-loss historical result — no meaningful improvement over market

On the same 3,440-match nested sample, the retained 10% RF market residual was also essentially indistinguishable from the market for `1X`, `X2`, and market-outsider-or-draw probabilities.

- `1X`: RF Brier +0.000067 and log loss +0.000145 versus market (slightly worse).
- `X2`: RF Brier -0.000013 and log loss -0.000010 versus market (tiny improvement, far below evidence for promotion).
- market outsider + draw: RF Brier +0.000032 and log loss +0.000096 versus market (slightly worse).

**Decision:** Non-loss remains a useful proposition and price lens, but there is no historical basis here for claiming Football 1 improves its probability over the market. The research value now lies in comparing our fair construction and real/synthetic double-chance prices prospectively.

## Interface requirement — deliberately deferred

No Swift interface redesign is part of this implementation step.

The backend output is intentionally shaped so that a later interface can present, without recomputing research logic:

- Result Call;
- Best Price;
- Result + Price status;
- Draw Profile;
- 1X / X2 fair probabilities and fair odds;
- outsider non-loss / favourite vulnerability;
- supporting market and model discrepancies;
- slate-relative category leaders.

The likely product hierarchy remains:

**Prophet → Trader → Draw/Shape → Non-Loss → Portfolio**

The final information density, labels, confidence language and card hierarchy should be designed only after the research layer has settled. “Clarity is king” remains the interface constraint.

### Elo chart scaling requirement

When interface work resumes, the Elo charts must not use such a wide fixed vertical scale that meaningful differences between teams are visually compressed. The chart should use a tighter data-relative domain, with enough padding to avoid exaggeration while still making real separation legible. This is a presentation fix only; it must not alter Elo values or model calculations.

## Promotion rule

All new outputs in this layer are research-only with zero decision weight. Before any label such as `HIGH`, `INTERESTING`, `ACT`, or `BET` receives operational meaning, Football 1 must freeze the rule and test it prospectively on untouched observations.
