# Portfolio Monte Carlo and Casino Lessons

Status: historical exploratory research only. Decision weight: 0. Product activation: none.

## Why Monte Carlo belongs in Football 1

Monte Carlo is not being used as a betting system and it is not allowed to manufacture an edge. It is used to answer path-risk questions that one historical equity curve cannot answer:

- How often does a portfolio finish above its starting bankroll?
- How often does it suffer a 25%, 50% or 75% drawdown?
- What does the worst 5% of simulated terminal outcomes look like?
- How much capital is typically exposed under each staking rule?
- Given an explicit low-risk hurdle, how often does the simulated betting portfolio finish above it?

The source selections remain the already-inspected historical OOS Football 1 selections. Resampling therefore describes the distribution implied by that history; it is not fresh confirmation and it cannot establish future profitability.

## Week-block bootstrap

Portfolio Monte Carlo v1 resamples whole calendar weeks with replacement rather than shuffling individual bets independently.

Reasons:

1. Bets within the same football week can share league, form, weather, news, sentiment and market regime effects.
2. A cluster of bad results on one weekend should remain a cluster in a resampled path.
3. Empty weeks are retained. They matter to calendar-based risk controls such as the previous-week-loss throttle.
4. Every strategy receives the same sampled week sequence so comparisons are paired.

This still does not make weeks iid. It is a practical stress test, not a generative model of future football.

## First frozen-data result

Run policy:

- frozen 4 September canonical database,
- 2,000 simulations,
- 40-week horizon,
- 461 historical source week blocks,
- starting bankroll 1,000,
- base stake 1%,
- illustrative 4% annual hurdle only (40-week terminal target 1,030.63),
- same sampled weeks for all strategies.

### Gold-standard selections

| Strategy | Median terminal bankroll | Mean terminal bankroll | P(finish > start) | P(finish > illustrative 4% hurdle) | 95th pct max drawdown | P(max DD >=25%) | Worst 5% mean terminal |
|---|---:|---:|---:|---:|---:|---:|---:|
| Flat stake | 973.65 | 974.30 | 39.95% | 28.85% | 23.61% | 3.65% | 755.32 |
| Bankroll proportional | 968.40 | 974.46 | 37.70% | 27.15% | 21.59% | 1.70% | 779.57 |
| Drawdown throttle | 965.22 | 979.11 | 34.00% | 23.05% | 13.95% | 0.00% | 863.47 |
| Previous-week-loss throttle | 970.79 | 979.35 | 37.20% | 26.00% | 17.80% | 0.25% | 821.53 |

Interpretation:

- The central tendency remains negative. No staking rule creates an edge.
- Flat staking offers the highest chance of finishing above the illustrative hurdle, but also the weakest downside protection.
- The drawdown throttle materially compresses the left tail: no simulated path lost 25% or more of starting capital at the terminal point, and none reached a 25% maximum drawdown in this 2,000-path sample.
- The cost of that protection is lower upside participation and lower probability of finishing above the illustrative hurdle.
- The previous-week-loss throttle is a middle ground, but remains an exploratory risk rule rather than a validated policy.

### Market-favourite benchmark

Betting the market favourite every eligible match was materially more dangerous over the same sampled week paths:

- median terminal bankroll: 880.70,
- mean terminal bankroll: 882.54,
- probability finish above start: 24.85%,
- probability finish above illustrative 4% hurdle: 20.20%,
- median maximum drawdown: 24.39%,
- 95th-percentile maximum drawdown: 45.47%,
- probability of at least a 25% maximum drawdown: 47.55%,
- probability of terminal loss of at least 25%: 22.90%,
- worst 5% mean terminal bankroll: 526.32.

This is a benchmark, not evidence that the Football 1 selection class is profitable. It shows that indiscriminate participation can be much more destructive than selective participation plus risk control.

## Casino lessons worth keeping

### 1. Staking does not create expected value

Martingale, D'Alembert, Fibonacci and other progression systems change the distribution and timing of losses. They do not remove a house edge. Football 1 therefore forbids loss-chasing logic that increases stake because the previous bet or week lost.

### 2. Survival matters even with a real edge

Advantage players such as card counters distinguish edge from bankroll survival. A small genuine edge can still experience long negative runs. Football 1 should therefore report drawdown and capital-loss probabilities alongside return.

### 3. Bet more only when the information state is better

The useful analogy to card-counting bet spreads is conditional exposure: stake can rise only when independently validated evidence indicates a better information state. It must not rise merely because the model-market residual is numerically larger; Football 1's own residual-magnitude audit found that larger deviations were historically less reliable.

Portfolio v2 may later test symmetric conviction multipliers, but those remain disabled until the conviction ranking demonstrates monotonic historical quality and then survives prospective confirmation.

### 4. Table limits have a Football 1 analogue

A hard portfolio cap is useful even when a model looks attractive. Candidate future controls include:

- maximum fraction of bankroll on one match,
- maximum aggregate exposure in one matchweek,
- maximum correlated exposure to one club or outcome class,
- drawdown-based risk throttling,
- no borrowing/replenishment assumptions inside the portfolio simulation.

These are capital constraints, not probability features.

## Treasury / low-risk benchmark policy

The simulator accepts an optional annual benchmark rate and compounds it over the simulated horizon. This is deliberately generic.

A claim that Football 1 has "beaten Treasuries" requires more discipline:

- define the benchmark before the prospective period,
- use an observed contemporaneous return/yield appropriate to the chosen instrument,
- keep currency consistent with the user's portfolio or explicitly model FX/hedging,
- compare over the same elapsed period,
- report drawdown and volatility as well as terminal return,
- do not substitute an illustrative rate for an observed Treasury result.

For a CHF-denominated user, an unhedged USD Treasury position is not risk-free in CHF because USD/CHF movement can dominate the bond return. A future product benchmark should therefore be explicit about base currency.

## Behavioural product implication

Football 1 should make restraint visible without turning restraint into deprivation. Portfolio outputs can show capital preserved, exposure avoided and PASS decisions respected. Matchday predictions can provide engagement even when no real-money candidate qualifies.

No feature should use hypothetical missed jackpots, accumulator FOMO, loss-chasing prompts or escalating stake streaks to increase wagering frequency.

A future voluntary sharing/observer feature for a partner or trusted person could be considered only with explicit user control and privacy safeguards. It is not part of Portfolio v1 or v2.

## Current implementation

`src/football1/portfolio_monte_carlo.py` provides:

- calendar-week source-block construction,
- empty-week retention,
- seeded reproducible sampling,
- paired paths for flat, bankroll-proportional, drawdown-throttled and previous-week-loss-throttled strategies,
- market-favourite flat-stake benchmark,
- terminal bankroll quantiles,
- worst-5% terminal mean,
- maximum-drawdown quantiles,
- probabilities of 25%/50% terminal capital loss,
- probabilities of 25%/50%/75% maximum drawdown,
- optional generic benchmark-beating frequency.

Governance remains:

- decision weight 0,
- no Martingale,
- no Kelly,
- no active conviction-upside sizing,
- no product staking recommendation.
