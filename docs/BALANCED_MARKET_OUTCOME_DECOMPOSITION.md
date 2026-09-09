# Balanced-Market Outcome Decomposition

Date: 9 September 2026

Status: historical post-hoc research; zero decision weight.

## Question

The Draw Possibility audit found that matches with closely balanced de-vigged Home and Away market probabilities produced materially more draws than the market's own pDraw implied. This follow-up asks where that excess draw mass comes from: Home, Away, or both?

The same already-inspected fixed H/A balance thresholds are retained: 2pp, 5pp and 10pp. No new threshold is chosen.

## Frozen data

- 5,340 completed EPL matches
- frozen 4 September canonical database
- SHA256 `4b5c751b22608026fb18eb190279c13b41d50ab88055057787c041ae4b841454`
- B365 pre-closing H/D/A odds, de-vigged for probability comparisons

## Overall EPL control

Across all 5,340 matches:

| Outcome | Market mean | Actual | Actual - market | Historical flat ROI |
| --- | ---: | ---: | ---: | ---: |
| Home | 44.32% | 44.57% | +0.25pp | -3.68% |
| Draw | 24.25% | 23.84% | -0.41pp | -6.41% |
| Away | 31.43% | 31.59% | +0.16pp | -4.12% |

The unconditional market is broadly well calibrated and all three flat bets lose.

## Balanced matches

### H/A gap <= 2pp — 184 matches

| Outcome | Market mean | Actual | Actual - market | Historical flat ROI |
| --- | ---: | ---: | ---: | ---: |
| Home | 35.72% | 36.41% | +0.69pp | -2.90% |
| Draw | 28.63% | 30.98% | **+2.35pp** | **+3.79%** |
| Away | 35.65% | 32.61% | **-3.04pp** | -12.48% |

### H/A gap <= 5pp — 469 matches

| Outcome | Market mean | Actual | Actual - market | Historical flat ROI |
| --- | ---: | ---: | ---: | ---: |
| Home | 35.87% | 36.03% | +0.16pp | -3.76% |
| Draw | 28.58% | 30.92% | **+2.33pp** | **+4.41%** |
| Away | 35.54% | 33.05% | **-2.49pp** | -11.23% |

### H/A gap <= 10pp — 964 matches

| Outcome | Market mean | Actual | Actual - market | Historical flat ROI |
| --- | ---: | ---: | ---: | ---: |
| Home | 36.26% | 35.27% | -0.99pp | -6.93% |
| Draw | 28.50% | 31.02% | **+2.51pp** | **+4.91%** |
| Away | 35.24% | 33.71% | **-1.52pp** | -8.49% |

## Season signs

For the <=10pp class across 15 observed seasons:

- Draw realized-minus-market residual was positive in **10/15** seasons.
- Away residual was negative in **10/15** seasons.
- Home residual was positive in 8/15 and negative in 7/15 — essentially mixed.
- Draw flat ROI was positive in 8/15 seasons.
- Away flat ROI was positive in only 4/15 seasons.

The tighter 2pp and 5pp classes tell a similar story: Draw residual is positive in 10/15 seasons and Away residual is negative in 10/15 seasons, while Home is much less directionally stable.

## Interpretation

The balanced-match Draw anomaly does **not** look primarily like a simple market overpricing of Home.

Historically, the excess realized draw mass is offset much more consistently by **Away underperformance relative to market probability**. In the tightest balance class, Home actually outperformed its market probability while Away underperformed by roughly three percentage points.

One plausible structural hypothesis is therefore:

> A market-balanced H/A fixture may often represent a stronger away side whose underlying superiority is approximately offset by the home side's venue advantage. The market can make the two win probabilities look equal while still underestimating the probability that those opposing forces cancel into a draw.

This is a hypothesis, not an established mechanism. It should not be described as causal and must not alter probabilities or recommendations.

A targeted follow-up may test whether balanced matches are disproportionately cases where a pre-match strength measure (for example raw Elo before venue adjustment) rates the away team as intrinsically stronger, and whether the Draw residual is concentrated in that subgroup.

## Governance

- Post-hoc historical research only.
- Decision weight 0.
- No probability adjustment.
- No threshold promotion.
- No stake or confidence rule.
- Historical B365 ROI is descriptive.
- The already-frozen 12–14 September Draw Possibility shadow remains the clean prospective test.
