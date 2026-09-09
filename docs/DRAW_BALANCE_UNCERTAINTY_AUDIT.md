# Draw Balance Uncertainty Audit

Date: 9 September 2026

Status: historical post-hoc uncertainty analysis; zero decision weight.

## Question

The Draw Possibility audit found excess realized draws in the fixed balanced-market classes. How surprising are those counts under each match's own bookmaker pDraw, once ordinary sampling variation and the fact that three related balance probes were inspected are acknowledged?

## Method

Frozen 4 September canonical EPL database, SHA256:
`4b5c751b22608026fb18eb190279c13b41d50ab88055057787c041ae4b841454`

For each already-fixed H/A balance class (<=2pp, <=5pp, <=10pp):

1. retain each match's individual de-vigged B365 pre-closing pDraw;
2. calculate the exact Poisson-binomial probability of observing at least the realized number of draws if those individual probabilities were correct and match outcomes were conditionally independent;
3. report an independence-based 95% normal interval for the observed-minus-expected draw-rate residual;
4. Holm-adjust the three one-sided tail probabilities across the nested probes;
5. retain a coarse season-level sign test: in how many seasons was realized draw count above the sum of market pDraw?

The Poisson-binomial independence assumption is optimistic relative to real football dependence across teams, seasons and regimes. The season-sign test is therefore useful as a deliberately coarse robustness check.

## Results

| H/A gap | Matches | Market expected draws | Actual draws | Residual rate | Exact one-sided p | Holm-adjusted p | Positive-residual seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| <=2pp | 184 | 52.67 | 57 | +2.35pp | 0.2639 | 0.2860 | 10/15 |
| <=5pp | 469 | 134.06 | 145 | +2.33pp | 0.1430 | 0.2860 | 10/15 |
| <=10pp | 964 | 274.79 | 299 | +2.51pp | **0.0461** | **0.1383** | 10/15 |

Independence-based 95% intervals for the draw-rate residual:

- <=2pp: **-4.18pp to +8.88pp**
- <=5pp: **-1.75pp to +6.42pp**
- <=10pp: **-0.34pp to +5.36pp**

Season-level one-sided sign-test p-value for 10 positive seasons out of 15: **0.1509** for each of the three nested classes.

## Interpretation

The broad <=10pp result is interesting but not secure historical proof.

If the <=10pp class had been the sole pre-specified test under an independence model, 299 observed draws versus 274.8 expected gives a one-sided exact tail probability of about 4.6%. But three nested balance probes were inspected, and a Holm correction raises the adjusted value to about 13.8%. The independence-based 95% interval also narrowly includes zero. Season-level direction is encouraging but only 10/15 seasons are positive, which is not unusual enough by itself to establish a persistent effect.

The tighter <=2pp and <=5pp classes have similar positive residual sizes but fewer matches and much larger uncertainty.

Therefore the correct status is:

> **Draw Possibility is a plausible structural/ranking clue with attractive historical economics, but the observed historical excess is not statistically strong enough to justify changing probability, fair price, selection or stake.**

This is a useful boundary. It prevents a +4.9% historical ROI from being mistaken for validation while preserving a falsifiable prospective hypothesis.

## Consequence

No further historical threshold refinement should be performed on this strand before prospective evidence arrives. The 12–14 September Draw Possibility shadow was frozen before those matches and is now the scientifically cleaner test.

The predeclared top two remain:

1. Bournemouth vs Brentford — Draw Possibility 99.21/100
2. Leeds vs Newcastle — Draw Possibility 95.02/100

Neither is a recommended bet. Draw Possibility remains a non-probability ranking observer with decision weight 0.

## Governance

- Preserve the unadjusted and adjusted uncertainty results together.
- No threshold promotion from the <=10pp historical result.
- No Draw probability boost.
- No fair-price or stake change.
- No further historical cutoff search before prospective settlement.
- Continue accumulating future frozen slates under the same score definition if the first prospective slate warrants it.
