# Football 1 — Draw Possibility Audit v1

**Status:** historical descriptive research, zero decision weight  
**Frozen data:** 4 September 2026 canonical EPL database  
**Matches:** 5,340  
**Purpose:** make draw-likeness analytically visible without pasting an artificial Draw weight into H/D/A probabilities.

## Question

A conventional 1X2 model asks which of Home, Draw or Away has the highest absolute probability. Because draws occur only roughly one quarter of the time, Draw will rarely be the argmax even in matches that are unusually draw-like.

This audit asks a different question:

> When the market itself sees the two teams as similarly likely to win, does the realized frequency of draws rise in a systematic way, and does the market's explicit Draw probability fully reflect that rise?

This is the first Football 1 use of **possibility** as distinct from probability:

- **Probability** remains the ordinary H/D/A probability used for fair pricing.
- **Draw Possibility** is a ranking/conditioning concept describing how draw-like the match shape is relative to other matches.
- Possibility is not a fourth probability, does not sum with H/D/A, and has no decision weight.

## Simplest possible shape variable

The audit deliberately begins with one transparent variable only:

`abs(de-vigged market P(Home) - de-vigged market P(Away))`

A smaller gap means the market sees the teams as more evenly matched.

Before running the historical audit, three fixed sensitivity thresholds were specified:

- Home/Away gap <= 2 percentage points
- Home/Away gap <= 5 percentage points
- Home/Away gap <= 10 percentage points

They are probes, not validated betting cutoffs.

## Overall draw baseline

Across all 5,340 matches:

- realized draws: **23.839%**
- mean de-vigged market Draw probability: **24.249%**
- realized minus market: **-0.410 percentage points**
- flat historical B365 Draw ROI: **-6.41%**

Blindly backing draws is therefore clearly negative in this sample.

## Home/Away balance bins

| De-vigged H/A probability gap | Matches | Draw rate | Mean market pDraw | Residual | Flat B365D ROI |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0–2pp | 184 | **30.98%** | 28.63% | **+2.35pp** | **+3.79%** |
| 2–5pp | 285 | **30.88%** | 28.56% | **+2.32pp** | **+4.81%** |
| 5–10pp | 495 | **31.11%** | 28.43% | **+2.68pp** | **+5.38%** |
| 10–15pp | 496 | 29.03% | 28.25% | +0.78pp | -1.14% |
| 15pp+ | 3,880 | 21.39% | 22.68% | -1.29pp | -9.90% |

The striking feature is not one optimized threshold. All three predeclared sub-bands inside 10pp independently land near a **31% realized draw rate**, while the market's mean Draw probability remains near **28.5%**.

## Fixed cumulative balance probes

The broad <=10pp class contains 964 matches:

- realized draw rate: **31.02%**
- all-match draw-rate lift: **1.30x**
- mean market pDraw: **28.50%**
- residual: **+2.51 percentage points**
- flat historical B365D ROI: **+4.91%**

Excluding the tiny 2026/27 partial season:

- matches: **959**
- draw rate: **31.07%**
- mean market pDraw: **28.51%**
- residual: **+2.56pp**
- flat historical B365D ROI: **+5.11%**

The <=5pp and <=2pp probes also remain positive after excluding the latest partial season.

## Ranking value

Treating smaller H/A gap as a continuous Draw Possibility ranking:

- closeness AUC for identifying draws: **0.59189**
- market pDraw AUC: **0.58896**

The closest 20% of all matches by H/A gap had:

- 1,068 matches
- **30.71%** realized draws
- **28.48%** mean market pDraw
- **+2.23pp** realized-minus-market residual
- **+4.01%** historical flat B365D ROI

The AUC advantage is small. It is nevertheless notable because this extremely simple balance measure marginally ranks draw outcomes better than the market's explicit Draw probability in the inspected history.

## Season stability

The aggregate result is not uniformly positive by season.

For the <=10pp class:

- positive realized draw residual vs market in **10 of 15** observed seasons
- positive flat B365 Draw ROI in **8 of 15** seasons

For <=5pp:

- positive residual in **10 of 15** seasons
- positive ROI in **9 of 15** seasons

For <=2pp:

- positive residual in **10 of 15** seasons
- positive ROI in **9 of 15** seasons

This is enough to reject an interpretation that the aggregate result comes from one isolated season, but not enough to call the effect stable or validated.

## Draw-rate trend over time

The user's separate hypothesis that EPL draws may have risen over time is **not supported as a simple monotonic trend** in this archive.

A descriptive linear fit to seasonal draw rates slopes downward by roughly **0.16 percentage points per season** including the tiny current season, and roughly **0.08 percentage points per season** excluding it.

Season-to-season variation is much larger than that slope. The appropriate future hypothesis is therefore a possible **draw regime** that changes over time, not a claim that EPL draw frequency has steadily increased because of rising money or tactical incentives.

## Interpretation

This result suggests a potentially useful distinction:

> Draw may be the wrong question for an H/D/A argmax, but the match can still be the strongest Draw-shaped match on a slate.

A future interface could therefore separate:

- **Most likely result:** ordinary H/D/A probability argmax
- **Draw Possibility:** relative draw-shape rank
- **Draw price assessment:** whether quoted Draw odds compensate for the estimated risk

For example, a match could honestly say:

`Most likely result: Home`

while also saying:

`TOP DRAW CANDIDATE — unusually balanced match shape`

There is no contradiction because these answer different questions.

## External clue

After the Football 1 hypothesis was raised, a relevant 2026 Journal of Sports Economics paper was identified: Bruce Lezana, *Fear of the Draw, Consumption and Mistaken Heuristics: Profit Opportunities in the Football Betting Market*. Its abstract reports EPL market inefficiencies with particularly strong results for draws and away teams using Markov and ordered-logit methods.

Football 1 has not used the paper to define or tune this audit. Its result should be treated as an independent literature clue worth later replication, not as validation of Football 1's balance result.

## Governance

- No existing Football 1 probability changes.
- No pasted Draw multiplier.
- No betting threshold promoted.
- No stake rule.
- Historical ROI is descriptive and already-observed data.
- Season diagnostics were inspected after the aggregate result and are robustness descriptions, not untouched confirmation.
- The next scientifically useful step is a **zero-weight prospective Draw Possibility shadow** frozen before future fixtures, preferably retaining the continuous H/A-gap rank and all originally specified balance bands rather than selecting a single flattering threshold.
