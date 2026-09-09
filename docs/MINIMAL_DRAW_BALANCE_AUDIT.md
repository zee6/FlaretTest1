# Minimal Draw Balance Incremental Audit

Date: 9 September 2026

Status: historical post-hoc research; zero decision weight.

## Question

After the Draw Possibility market-balance clue was observed, does absolute H/A market-probability balance add incremental information about draws beyond the bookmaker market's own draw probability?

This is deliberately a harder question than the original descriptive bucket audit. A balanced match may surface Draw as a useful *shape/ranking* concept even if adding that balance signal does not improve calibrated draw probability.

## Design

Frozen canonical EPL database from the 4 September audit:

- 5,340 completed matches total
- SHA256 `4b5c751b22608026fb18eb190279c13b41d50ab88055057787c041ae4b841454`
- B365 pre-closing H/D/A odds, de-vigged before use

Expanding chronological walk-forward by season:

- first 4 seasons used as minimum training history
- 11 held-out seasons
- 3,820 OOS matches

Three same-sample comparisons:

1. raw de-vigged B365 draw probability;
2. one-feature logistic recalibration using market pDraw only;
3. otherwise identical logistic model using market pDraw plus absolute `pHome - pAway` gap.

Fixed logistic `C=1.0`; no threshold search, no regularization search, no betting/staking rule.

## Aggregate OOS results

| Model | Brier | Log loss | AUC | ECE |
| --- | ---: | ---: | ---: | ---: |
| Raw market pDraw | 0.17570568 | 0.53406887 | 0.58082501 | 0.00897430 |
| pDraw-only recalibration | 0.17594236 | 0.53499903 | 0.58042852 | 0.01849176 |
| pDraw + H/A gap | 0.17602035 | 0.53503192 | 0.58215709 | 0.01833133 |

Incremental candidate minus pDraw-only control:

- Brier: **+0.00007799** (worse)
- log loss: **+0.00003288** (worse)
- AUC: **+0.00172857** (better)
- ECE: **-0.00016044** (slightly better)

Candidate minus raw market:

- Brier: **+0.00031468** (worse)
- log loss: **+0.00096305** (worse)
- AUC: **+0.00133208** (better)
- ECE: **+0.00935702** (worse)

The latest expanding-window fit gave standardized coefficients:

- market draw probability: **+0.13057**
- H/A probability gap: **-0.23211**

The negative gap coefficient is directionally consistent with the original clue: after conditioning on market pDraw, more evenly split Home/Away win probabilities are associated with higher fitted draw propensity.

## Season stability

Across 11 held-out seasons, adding H/A balance improved versus the pDraw-only recalibration in:

- Brier: **5/11 seasons**
- log loss: **5/11 seasons**
- AUC: **4/11 seasons**

This is not stable enough to promote.

## Interpretation

The result is mixed and useful.

H/A balance contains a small amount of incremental *ranking/discrimination* information: aggregate AUC improves slightly and the coefficient points in the expected direction. But it does **not** improve proper probability scoring. Brier and log loss both worsen slightly, seasonal stability is weak, and the raw market remains better calibrated.

Therefore the historical evidence supports the existing product/research separation:

> **Probability** answers how likely Draw is and remains anchored to calibrated H/D/A probabilities.
>
> **Draw Possibility** answers how unusually draw-shaped/balanced the match is and may be useful for ranking or surfacing candidates.

Draw Possibility must not currently alter fair probability, fair odds, stake, recommendation or confidence.

The already-frozen 12–14 September Draw Possibility shadow is the correct next test of ranking usefulness. It should remain unchanged.

## Governance

- Decision weight remains 0.
- No draw probability boost.
- No threshold promotion from historical ROI.
- No staking rule.
- No reinterpretation of Possibility as a probability percentage.
- Preserve negative proper-scoring result.
- Prospective evidence is required before any product decision weight.
