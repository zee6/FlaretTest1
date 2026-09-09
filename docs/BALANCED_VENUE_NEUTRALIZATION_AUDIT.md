# Balanced Venue-Neutralization Audit

Date: 9 September 2026

Status: historical post-hoc mechanism research; zero decision weight.

## Question

The balanced-market decomposition showed that excess Draw frequency was often offset by Away underperformance rather than a simple overpricing of Home. A plausible mechanism was therefore:

> market-balanced fixtures may often involve an intrinsically stronger away side whose underlying strength is offset by home venue advantage, increasing the chance of stalemate.

This audit tests that mechanism without introducing a fitted Elo threshold.

## Design

Frozen 4 September EPL database, SHA256:
`4b5c751b22608026fb18eb190279c13b41d50ab88055057787c041ae4b841454`

The already-inspected market-balance groups are retained unchanged: H/A de-vigged probability gap <=2pp, <=5pp and <=10pp.

Within each group, matches are split only by the sign of the existing strictly pre-match raw Elo feature:

- `away_elo_stronger`: home Elo minus away Elo < 0
- `home_elo_at_least_as_strong`: home Elo minus away Elo >= 0

The stored Elo difference is raw team strength; the +60 home-advantage term is not added to this stored feature. No Elo magnitude cutoff is fitted or searched.

## Results

### H/A gap <=2pp — 184 matches

**Away Elo stronger: 152 matches (82.6%)**

- mean raw Elo difference: -59.7
- market pDraw: 28.53%
- actual Draw: **31.58%**
- Draw residual: **+3.05pp**
- historical Draw ROI: **+6.16%**
- market pAway: 35.70%
- actual Away win: **28.95%**
- Away residual: **-6.76pp**

Home Elo at least as strong: 32 matches

- mean raw Elo difference: +29.5
- market pDraw: 29.09%
- actual Draw: 28.13%
- Draw residual: **-0.96pp**
- historical Draw ROI: **-7.50%**
- Away residual: **+14.59pp**

### H/A gap <=5pp — 469 matches

**Away Elo stronger: 381 matches (81.2%)**

- mean raw Elo difference: -58.1
- market pDraw: 28.50%
- actual Draw: **31.23%**
- Draw residual: **+2.73pp**
- historical Draw ROI: **+6.05%**
- Away residual: **-3.93pp**

Home Elo at least as strong: 88 matches

- mean raw Elo difference: +26.7
- market pDraw: 28.94%
- actual Draw: 29.55%
- Draw residual: **+0.60pp**
- historical Draw ROI: **-2.68%**
- Away residual: **+3.72pp**

### H/A gap <=10pp — 964 matches

Away Elo stronger: 780 matches (80.9%)

- mean raw Elo difference: -58.0
- market pDraw: 28.46%
- actual Draw: **30.51%**
- Draw residual: **+2.06pp**
- historical Draw ROI: **+3.55%**
- Away residual: **-1.98pp**

Home Elo at least as strong: 184 matches

- mean raw Elo difference: +32.0
- market pDraw: 28.71%
- actual Draw: **33.15%**
- Draw residual: **+4.44pp**
- historical Draw ROI: **+10.67%**
- Away residual: +0.39pp

## Season stability

For the away-Elo-strong subgroup, Draw residual was positive in 9/15 seasons at each of the 2pp, 5pp and 10pp balance definitions. Draw flat ROI was also positive in 9/15 seasons at each definition.

The home-Elo-at-least-as-strong subgroup is much smaller at tight balance. At <=2pp it had positive Draw residual/ROI in 6 of 12 observed seasons; at <=5pp, 8 of 14; at <=10pp, 11/15 positive Draw residual and 10/15 positive Draw ROI.

## Interpretation

The mechanism receives **partial support, not confirmation**.

The tightest balanced classes behave as hypothesised. Roughly four-fifths of near-even H/A markets involve an away side rated stronger on raw Elo. In those matches the away side substantially underperforms its market win probability and the Draw absorbs part of that missing outcome mass. The <=2pp and <=5pp home-Elo-strong controls do not show the same Draw pattern.

However, the broader <=10pp class does not preserve that clean separation: its smaller home-Elo-strong subgroup also has a large positive Draw residual and strong historical Draw ROI. Therefore venue-neutralised away strength cannot explain the entire balanced-match anomaly.

The useful structural finding is narrower:

> **Near-exact H/A market balance is often produced by an intrinsically stronger away side facing home advantage, and this configuration historically showed excess Draws. But balance itself appears to carry additional draw structure beyond that mechanism.**

No specific balance threshold is promoted from this post-hoc comparison.

## Governance

- Decision weight remains 0.
- No Draw probability adjustment.
- No threshold promotion.
- No stake, confidence or recommendation rule.
- No causal claim about venue neutralisation.
- Preserve the broader <=10pp counterexample.
- The already-frozen 12–14 September Draw Possibility shadow remains unchanged and is the required prospective evidence path.
