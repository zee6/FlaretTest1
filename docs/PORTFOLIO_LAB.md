# Football 1 Portfolio Laboratory v1

**Status date:** 7 September 2026  
**Status:** historical exploratory research on previously inspected data  
**Decision weight:** 0.0  
**Promotion allowed:** no

## Purpose

Portfolio Laboratory v1 asks a deliberately different question from Prophet and Trader:

> If the underlying selections are imperfect, can disciplined stake management reduce capital damage without pretending to improve the football probabilities?

The laboratory is a risk-control experiment, not evidence of a profitable betting system.

Previous portfolio P&L never changes Home / Draw / Away probabilities. Previous losses may alter only the amount of capital exposed.

## Reproducibility

Merged in PR #44 at master merge commit `e3590034005573a1940ae1f1eac0ba85796af0e5`.

Master workflow run: `34165194730` — success.  
Tests in that run: **198 passed**.

The workflow reused the frozen 4 September canonical database:

- source audit run: `33924106948`
- source head: `ada0ebe987323389870d80aca0234be11c18b53d`
- database SHA-256: `4b5c751b22608026fb18eb190279c13b41d50ab88055057787c041ae4b841454`

## Illustrative portfolio parameters

These parameters were declared before running this portfolio comparison and were **not historically optimized**:

- starting bankroll: 1,000 units
- base stake fraction: 1% of bankroll/reference bankroll
- flat stake: 10 units
- drawdown scale: 20%
- drawdown minimum stake multiplier: 25%
- previous-week-loss multiplier: 50%

They must not be treated as validated optimal values.

## Selection sets

### Gold standard structural class

1,207 historical bets.

The Football 1 H/D/A result call had raw positive model EV at the quoted Bet365 price **and** that result was also the highest-EV H/D/A outcome.

This is a structural product class only. Earlier research already showed it did not establish genuine positive expected value.

| Staking method | Final bankroll | Turnover ROI | Max drawdown | Longest losing streak |
| --- | ---: | ---: | ---: | ---: |
| Flat 10-unit stake | 680.30 | -2.65% | 38.80% | 8 |
| 1% current-bankroll proportional | 681.92 | -3.06% | 36.43% | 8 |
| Drawdown throttle | **828.48** | -3.84% | **20.06%** | 8 |
| Previous-week-loss throttle | 709.54 | -3.70% | 32.06% | 8 |

The drawdown throttle reduced maximum drawdown by about **48% relative to flat staking** (38.80% to 20.06%). It also preserved substantially more of the starting bankroll.

However, its turnover ROI was worse than flat staking. The improvement therefore came from **reducing exposure while the selection process was losing**, not from creating predictive or pricing edge.

The previous-week-loss throttle also reduced maximum drawdown, but more modestly: about **17% relative to flat staking**.

### Broad result + price class

1,299 historical bets.

The Football 1 H/D/A result call had raw positive model EV at the quoted Bet365 price, without requiring that it also be the highest-EV outcome.

| Staking method | Final bankroll | Turnover ROI | Max drawdown | Longest losing streak |
| --- | ---: | ---: | ---: | ---: |
| Flat 10-unit stake | 520.90 | -3.69% | 52.91% | 8 |
| 1% current-bankroll proportional | 579.09 | -4.31% | 45.71% | 8 |
| Drawdown throttle | **803.98** | -5.64% | **22.42%** | 8 |
| Previous-week-loss throttle | 667.69 | -4.16% | 35.96% | 8 |

Again, the drawdown throttle protected capital strongly while the underlying selection set remained negative. Maximum drawdown fell by about **58% relative to flat staking**.

## Naive market-favourite benchmark

A separate benchmark bet the de-vigged Bet365 market favourite in every eligible OOS match with a constant 10-unit stake.

- bets placed before bankroll exhaustion: 3,650
- final bankroll: 0.00
- turnover ROI: -2.74%
- maximum drawdown: 100%
- longest losing streak: 8

This is not an apples-to-apples selection benchmark because it bets far more often than the Football 1 classes. Its purpose is to show the capital consequences of repeatedly betting favourites without a protective portfolio rule.

## Interpretation

The first Portfolio result is useful precisely because it does **not** rescue the betting model.

1. None of the tested staking methods made the underlying historical selections profitable.
2. Drawdown-aware exposure control substantially reduced maximum drawdown and preserved capital.
3. The lower losses came from staking less during adverse portfolio states, not from improved prediction.
4. A losing week may therefore be relevant to the **risk budget**, but must never feed back into the football probability model.
5. Larger Football 1 model residuals must not be used for larger stake sizes: the separate residual-magnitude audit found that larger deviations were historically less reliable, not more reliable.
6. Kelly-style sizing remains disabled because Football 1 probabilities are not sufficiently calibrated to justify it.

The governing product distinction is:

> **Prophet estimates the match. Trader evaluates the price. Portfolio controls how much capital, if any, should be exposed.**

## Implemented future UI contract

The backend report already exports:

- equity curves for each strategy;
- an immutable-style per-bet journal;
- match date;
- selected outcome;
- odds;
- stake;
- P&L;
- post-bet bankroll;
- drawdown fraction.

This supports a future Portfolio page with multiple comparison lines such as:

- Football 1 portfolio policy;
- same selections with flat stake;
- favourite-only benchmark.

The Swift interface remains deliberately deferred until the risk-control research design is more settled.

## Next research requirements

Do **not** tune the 1%, 20%, 25% or 50% parameters to this already observed history.

Useful next steps include:

- test predeclared portfolio policies prospectively with virtual capital;
- add exposure/concentration controls when multiple fixtures overlap in time;
- examine same-team and correlated-event exposure;
- compare risk-adjusted metrics in addition to final P&L and drawdown;
- only investigate rank-weighted sizing after a ranking variable demonstrates genuine calibration/reliability;
- separately audit recency/time-decay in the football models, without allowing portfolio P&L to influence prediction.
