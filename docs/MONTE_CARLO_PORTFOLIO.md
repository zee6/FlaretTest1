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
