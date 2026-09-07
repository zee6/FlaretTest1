# Recency Extension and Venue-Recency Audit

Date: 8 September 2026

Status: historical exploratory evidence on previously inspected data. Decision weight 0. No model, half-life, selection rule or staking rule is promoted by this document.

## Frozen comparison sample

The audit reuses the frozen canonical EPL database from the successful 4 September 2026 audit. The paired walk-forward evaluation contains 4,200 held-out matches. The benchmark is de-vigged Bet365 pre-closing H/D/A probability.

Market benchmark:

- log loss: 0.960278899
- Brier: 0.569004977
- accuracy: 54.88%
- top-label ECE: 0.020084578

The existing equal-weight fixed-market residual remains:

- log loss: 0.962730147
- Brier: 0.570341789
- accuracy: 54.55%
- top-label ECE: 0.014971019

It remains worse than the market overall.

## 15-day overall-form recency extension

This extension was requested after the original 30/60/120-day recency history had already been inspected. Therefore the 15-day result is explicitly post-hoc exploratory evidence, not untouched confirmation.

| Form weighting | Log loss | Brier | Top-label ECE | LL delta vs equal weight | Brier delta vs equal weight |
| --- | ---: | ---: | ---: | ---: | ---: |
| Equal weight | 0.962730147 | 0.570341789 | 0.014971019 | 0 | 0 |
| 15-day half-life | 0.962323767 | 0.570149227 | 0.018056281 | -0.000406379 | -0.000192562 |
| 30-day half-life | 0.962397233 | 0.570171403 | 0.017577433 | -0.000332914 | -0.000170386 |
| 60-day half-life | 0.962524432 | 0.570229646 | 0.015040415 | -0.000205715 | -0.000112143 |
| 120-day half-life | 0.962627877 | 0.570279903 | 0.015298562 | -0.000102269 | -0.000061886 |

Observations:

- The 15-day probe is the best of these inspected recency variants on aggregate log loss and Brier.
- It improves log loss versus equal weighting in 8 of 12 held-out seasons and Brier in 7 of 12.
- Excluding the very small 2026/27 held-out sample, its aggregate improvement remains: approximately -0.000360 log loss and -0.000162 Brier versus equal weighting.
- Calibration is worse than the equal-weight residual: top-label ECE rises from 0.01497 to 0.01806.
- Most importantly, even the 15-day variant remains worse than the market: log loss 0.962324 versus 0.960279.

Interpretation: short recency remains a plausible research lead, but there is still no evidence that it creates market-beating probabilities. The already-frozen 30-day prospective shadow remains scientifically cleaner than replacing it retrospectively with 15 days after observing this result.

## Home-only / away-only recency audit

The venue experiment asks a different question. For each fixture:

- the home side is summarized using only its prior EPL home matches;
- the away side is summarized using only its prior EPL away matches;
- those role-specific histories are exponentially decayed by calendar age;
- 15/30/60/120-day half-lives were declared before this venue-recency run;
- the market anchor, base Football 1 features, residual architecture, alpha, season walk-forward splits and same-day leakage protection remain unchanged.

The equal-weight home/away control itself is slightly worse than the fixed residual:

- equal-weight venue log loss: 0.963042972
- equal-weight venue Brier: 0.570596819
- fixed residual log loss: 0.962730147
- fixed residual Brier: 0.570341789

Venue recency results:

| Venue weighting | Log loss | Brier | Top-label ECE | LL delta vs equal-weight venue | Brier delta vs equal-weight venue |
| --- | ---: | ---: | ---: | ---: | ---: |
| Equal-weight home/away | 0.963042972 | 0.570596819 | 0.012594056 | 0 | 0 |
| 15-day half-life | 0.963307667 | 0.570738281 | 0.017332678 | +0.000264695 | +0.000141462 |
| 30-day half-life | 0.963250990 | 0.570704772 | 0.015486546 | +0.000208018 | +0.000107953 |
| 60-day half-life | 0.963127474 | 0.570646549 | 0.013176339 | +0.000084502 | +0.000049729 |
| 120-day half-life | 0.963054302 | 0.570603324 | 0.013077986 | +0.000011330 | +0.000006505 |

All four venue-recency variants are worse than the equal-weight venue control on aggregate log loss and Brier. The faster the venue decay, the larger the aggregate deterioration; 15 days is the worst of the tested venue variants.

Season counts are also not compelling. The 15-day and 30-day venue variants improve log loss versus equal-weight venue form in only 5 of 12 held-out seasons.

## Crowd / supporter interpretation guard

This audit does **not** test whether particular supporters are hostile, loyal, forgiving or demanding. It tests only a measurable proxy: whether recent home-only and away-only team performance should receive greater statistical weight.

A true crowd-pressure effect could be obscured by team quality, injuries, managers, tactics, schedule, stadium characteristics, finances, expectations and many other variables. Conversely, a positive venue-recency result would not by itself prove crowd causality.

The negative result therefore says only: **simple exponentially decayed home-only/away-only form does not improve the frozen market-anchored residual on this history.**

A more targeted future crowd/venue experiment, if pursued, should distinguish team-specific home response from ordinary venue form—for example, recent home performance relative to the same team's general form or market expectation—rather than merely using home-form minus away-form differences.

## Governance conclusion

1. Preserve the existing 30-day prospective recency shadow unchanged; do not rewrite it to 15 days after seeing this history.
2. Record 15-day overall recency as a promising but post-hoc zero-weight research lead.
3. Do not promote venue-recency weighting. The first simple role-specific recency proxy is a negative result.
4. Any finer crowd/venue hypothesis must be a separately specified experiment and cannot inherit a positive interpretation from the 15-day general-form result.
