# Portfolio Laboratory v2 — Symmetric Exposure / Upside Sizing Spec

Date: 8 September 2026

Status: research specification only. No stake multiplier in this document is approved for betting, product use or prospective decision weight.

## Motivation

Portfolio Laboratory v1 showed that reducing stake after portfolio stress can materially reduce capital damage even when the underlying selections remain unprofitable. That is useful risk control, but it is only one side of portfolio management.

If Football 1 eventually develops reliable finer-resolution evidence about which opportunities are genuinely stronger than others, the same portfolio layer should be able to **increase exposure selectively**, not merely reduce it.

The intended architecture is symmetric:

`final stake = base stake × conviction multiplier × portfolio-risk multiplier`

where:

- the **conviction multiplier** reflects the estimated quality of the current opportunity;
- the **portfolio-risk multiplier** reflects the current health of the bankroll / drawdown state;
- neither multiplier changes the underlying football probability after the fact.

This separation prevents a losing streak from rewriting the football model, and prevents a compelling football story from overriding portfolio risk limits.

## Why raw model disagreement is not enough

Football 1 has already observed that larger model residuals versus the bookmaker market were not more reliable on inspected history. Therefore:

- do not increase stake merely because `Football1 probability - market probability` is numerically large;
- do not use raw EV magnitude as an automatic staking rank;
- do not enable Kelly sizing from the current fair probabilities;
- do not let one juror dominate stake size simply because its signal is extreme.

A larger stake requires **evidence quality**, not merely a larger point estimate.

## Candidate conviction evidence

The future conviction layer may combine independently evaluated signals such as:

1. **Price quality** — quoted odds remain attractive after conservative fair-price estimation and calibration adjustment.
2. **Result-jury agreement** — multiple sufficiently independent jurors support the same H/D/A direction.
3. **General recency confirmation** — a frozen recency model supports the same direction and has prospective evidence of incremental usefulness.
4. **Venue / matchup confirmation** — only if a venue or matchup juror independently validates. The first simple venue-recency audit is negative and therefore receives zero positive sizing weight.
5. **Movement confirmation** — price movement model supports acting now rather than waiting, after prospective validation.
6. **Uncertainty / calibration** — high model uncertainty reduces conviction even when the point estimate looks attractive.

Every signal begins at weight zero. Historical attractiveness alone cannot activate a sizing weight.

## Example archetype: strong contender at home versus deteriorating opponent

This is a useful *archetype*, not a rule.

A fixture might accumulate evidence because:

- the home side is objectively strong;
- the opponent's recent general form is deteriorating;
- several independent jurors agree on the home result;
- the home side is not showing adverse lineup / congestion / tactical evidence;
- the current bookmaker price is still longer than Football 1's conservative fair price;
- movement evidence suggests the price is more likely to shorten than drift.

However, the bookmaker will usually already charge heavily for home advantage, team reputation and obvious form. Therefore a strong team at home is **not automatically a larger bet**. It qualifies for increased exposure only when the *price* remains favourable after the evidence is accounted for.

## Research ladder

For an initial laboratory implementation, the portfolio engine should support a bounded illustrative ladder such as:

- weak / conflicting evidence: 0.50× base stake
- ordinary qualified opportunity: 1.00×
- strong multi-signal agreement: 1.25×
- exceptional multi-signal agreement: 1.50×

These numbers are placeholders for mechanics testing, not optimized values and not approved thresholds. A first implementation should cap conviction at 1.50× rather than introduce high leverage.

The portfolio-risk multiplier remains independent. Example:

- conviction multiplier = 1.50×
- drawdown multiplier = 0.50×
- final multiplier = 0.75× base stake

Thus high conviction cannot automatically override capital preservation.

## Required validation sequence

Before any upside multiplier can receive decision weight:

1. define the evidence score without looking at the future evaluation sample;
2. freeze its mapping to stake tiers;
3. compare the same selections under flat, downside-only and symmetric sizing;
4. report final bankroll, turnover, ROI, max drawdown, losing streak, tail loss and concentration;
5. test whether higher conviction tiers actually have better calibration / realized return than lower tiers;
6. confirm the ranking prospectively on untouched fixtures;
7. only then consider allowing conviction to alter stake size.

If higher tiers do not monotonically improve outcome quality, the sizing signal fails even if one historical bankroll path looks attractive.

## Relationship to current recency findings

General form recency currently shows a small historical improvement over equal weighting. The 15-day probe is slightly stronger historically than 30 days, but is post-hoc, worsens calibration and still loses to the market. The existing 30-day prospective shadow therefore remains the cleaner test.

Simple home-only / away-only recency is currently a negative result and should not contribute positive conviction weight.

This means Portfolio v2 can be built mechanically now, but **upside sizing should remain disabled until at least one finer-resolution signal demonstrates prospective ranking value.**

## UI implication

Eventually the Portfolio screen should be able to explain stake size as separate components, for example:

- Base risk: 1.00%
- Conviction: 1.25×
- Drawdown control: 0.80×
- Final risk: 1.00% of current bankroll

This is preferable to an unexplained single stake recommendation. It preserves the project's core product principle: clarity first.
