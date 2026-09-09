# Bet Check — Deterministic Local Core v1

Status: backend/data-contract implementation. No product recommendation or Swift UI activation.

## Purpose

Bet Check lets a user inspect a bet they are already considering rather than requiring Football 1 to manufacture more betting opportunities.

The intended eventual Apple-device path is:

`bet slip screenshot / manual entry`
→ `Apple Vision OCR or manual form`
→ `local market parser / ontology`
→ `structured BetCheck input`
→ `deterministic Football 1 Bet Check core`
→ `SwiftUI explanation`

The core reasoning does **not** require an LLM, cloud reasoning or a server. Fresh market prices and fresh Football 1 data may require a network fetch, but once those values are present the evaluation is ordinary deterministic arithmetic suitable for Swift on Apple silicon.

## V1 scope

Bet Check v1 supports only EPL 1X2 (`h2h`) legs:

- Home,
- Draw,
- Away.

The evaluator accepts a structured bet and structured event references. OCR is deliberately outside the core. This makes the reasoning contract testable before bookmaker-specific text parsing is attempted.

Example bet input:

```json
{
  "currency": "GBP",
  "stake": 10.0,
  "quoted_combined_odds": 7.5,
  "legs": [
    {
      "event_id": "event-a",
      "market": "h2h",
      "outcome": "home",
      "quoted_odds": 2.0
    },
    {
      "event_id": "event-b",
      "market": "h2h",
      "outcome": "away",
      "quoted_odds": 4.0
    }
  ]
}
```

Reference data for each event contains:

- market de-vigged H/D/A probabilities,
- Football 1 H/D/A probabilities,
- optional best observed sportsbook price and provenance,
- home/away labels.

## Per-leg output

Each leg is decomposed into separate concepts:

1. **User quote** — entered decimal odds and break-even probability.
2. **Market benchmark** — de-vigged market probability and market fair odds.
3. **Football 1 view** — model probability, fair odds and model-market residual.
4. **Best observed price** — if synchronized price data exists, including bookmaker provenance.
5. **Price quality** — exact best, within 1%, within 2%, materially below best, better than the observed board, or unknown.

A better bookmaker quote is never allowed to alter the probability estimate. Price quality and football confidence are separate dimensions.

## Weakest leg

For multi-leg bets, Bet Check identifies a weakest leg using the conservative de-vigged market benchmark at the user's entered price. The primary ordering is the lowest market arithmetic EV; price shortfall versus the observed best breaks ties.

This deliberately does **not** use the largest Football 1 residual as a conviction score because historical research found residual magnitude was not more reliable.

The weakest-leg output is explanatory, not a betting instruction.

## Accumulators

### Distinct matches

For legs from different event IDs, v1 may display a combined probability formed by multiplying the leg probabilities. It is explicitly labelled:

`independence_only_distinct_events`

This is a mathematical approximation for explanation, not a validated joint model.

### Same-match / Bet Builder legs

If more than one leg refers to the same event ID, v1 refuses to multiply the probabilities and returns:

`unsupported_correlated_same_event`

A same-match Bet Builder can contain strong dependence between legs. Football 1 must not create a plausible-looking fair combined price until a joint/correlated market model exists for those market types.

## Combined-price inspection

If the user supplies a bookmaker's combined accumulator price, Bet Check compares it with the simple product of the entered leg prices.

This can expose a combined quote that is worse than the visible leg prices without making any claim about whether the accumulator should be placed.

## Price-quality language

Price labels describe only the quote:

- `best_observed`
- `near_best_within_1pct`
- `near_best_within_2pct`
- `materially_below_best`
- `better_than_observed_best`
- `best_price_unknown`

A future product can therefore say:

> Your 2.18 is within 1% of the 2.20 best observed price.

without implying:

> This is a good bet.

That distinction is central to Football 1.

## On-device requirement

The Python implementation is the research/source-of-truth contract. A future Swift implementation should reproduce the same calculations exactly and be covered by Python→Swift regression fixtures.

Expected device responsibilities:

- Vision OCR: on-device where practical,
- bet-slip text normalization: local rules / compact parser,
- event/market matching: local ontology plus downloaded fixture data,
- probability/price arithmetic: local Swift,
- explanation templates: local Swift,
- portfolio impact: local Swift,
- live best-price refresh: network data fetch only when requested.

No LLM is required for the core feature.

## Governance

- EPL currency is GBP.
- V1 supports 1X2 only.
- Bet Check never places a bet.
- Raw positive model EV is not a recommendation threshold.
- Football 1 residual magnitude is not confidence.
- Same-event joint probabilities are refused until supported by a real joint model.
- Affiliate status cannot affect best-price ordering or analysis.
- User-entered price, market consensus, Football 1 fair price and best observed price remain separately visible concepts.
