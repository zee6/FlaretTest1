# Best Price Policy

Status: product/data-contract policy. No bookmaker commercial integration is active.

## Principle

Football 1 is an analytical fair-price product. When evaluating an available wager, the analytical price should be the best genuinely observed quote in the eligible bookmaker universe at the recorded snapshot time.

That assumption is allowed because Football 1 is comparing prices, not claiming that every user can transact at every bookmaker.

The user-facing product should distinguish:

1. Football 1 fair odds,
2. de-vigged market consensus,
3. best observed bookmaker odds,
4. the bookmaker supplying that quote,
5. quote/snapshot time,
6. the breadth of the bookmaker universe searched.

## Find best price

A future `Find best price` action should:

- query or refresh the supported bookmaker universe,
- rank quotes solely by decimal price for the selected outcome,
- show the best quote first and optionally the remaining quote board,
- show when the price was observed,
- leave account availability, eligibility and transaction execution to the user,
- never imply that a quoted price is guaranteed until the user reaches the bookmaker,
- never place a bet.

A useful compact contract is:

`BEST PRICE 2.24 — Bookmaker X — observed 20:14 UTC — 14 complete books`

The bookmaker count matters because "best" is always conditional on the searched universe.

## Commercial separation

Future bookmaker affiliate or sponsorship relationships must not affect:

- Football 1 fair probabilities,
- market consensus,
- which fixtures are surfaced,
- candidate ranking,
- stake sizing,
- bookmaker ordering,
- best-price determination,
- explanatory text about price quality.

The best-price algorithm must remain a pure comparison over observed eligible quotes. A commercial relationship may add a clearly labelled outbound link only after the analytical ranking is complete.

If a partner bookmaker does not offer the best observed price, it must not be promoted above the bookmaker that does.

This separation is central to Football 1 credibility.

## Currency policy

Portfolio currency should default to the competition's home currency rather than to the user's residence:

- English Premier League: GBP.

Future competitions can define their own canonical portfolio currency in competition metadata. Odds themselves are dimensionless; currency applies to bankroll, stake, P&L and benchmark reporting.

V1 should remain English-language. Multi-language product localization is deferred until there is a clear commercial reason, because vocabulary drift across analytical terms would create avoidable maintenance and interpretation risk.

## Historical research

Historical backtests should separately report:

- principal benchmark price (currently historical B365 pre-closing where frozen protocol requires it), and
- best-observed-price research when a trustworthy multi-book historical universe exists.

These must not be conflated. Historical best price is only legitimate when quote timing and bookmaker availability are known.

## Responsible product implication

`Find best price` should be framed as price comparison, not as an encouragement to open more accounts or increase wagering frequency.

Football 1 should never calculate hypothetical missed jackpots from bookmakers a user did not use.
