# Best Price Economics — Prospective Observer v1

Status: prospective quote-structure research. Decision weight: 0. Product activation: none.

## Question

How much economic value is available from shopping the price of the *same* EPL outcome at the *same* moment, without changing Football 1 probabilities or selection logic?

This is deliberately different from asking whether Football 1 predicts football better than the market. A better quote improves payout and lowers break-even probability even if the underlying probability estimate is unchanged.

## Data

Source: `prospective/odds_snapshots.jsonl`.

The first audit contains:

- 38 immutable pre-kickoff event snapshots,
- 114 H/D/A outcome quote observations,
- two archived quote times covering 19 fixtures,
- 14–18 directly comparable sportsbook quotes per outcome, median 15,
- GBP as the EPL portfolio currency.

The full quote boards were archived at:

- 2026-09-04 21:37:56 UTC,
- 2026-09-05 10:30:42 UTC.

The original 20 prediction locks were made earlier. No full quote board exists in the durable archive at the exact original lock timestamps, so this audit does **not** mix later bookmaker boards with earlier Football 1 probabilities. Exact locked-model price attribution remains unavailable for this first sample.

## Sportsbooks versus exchanges

Known exchanges in the UK feed are excluded from the default best-price benchmark:

- Betfair Exchange,
- Matchbook,
- Smarkets.

Their raw back prices remain visible as a diagnostic, but exchange commission is not encoded in the archived raw price and can vary by venue/account terms. Comparing a raw exchange price directly with a sportsbook decimal price would therefore be potentially flattering.

Raw exchange prices exceeded the best directly comparable sportsbook quote in 77 of 114 observations. This is interesting, but it is not a net-price result and earns no product preference from this audit.

## Main result

Across all 114 outcome observations:

- mean best-sportsbook versus median-sportsbook gross-return uplift: **+4.3754%**,
- median uplift: **+3.5714%**,
- 90th percentile uplift: **+8.3333%**,
- mean best versus mean sportsbook quote: **+4.2837%**,
- mean best versus worst sportsbook quote: **+9.3538%**,
- mean break-even probability reduction versus the median quote: **1.2176 percentage points**.

Frequency:

- best quote at least 1% above median: **96.49%**,
- at least 2% above median: **83.33%**,
- at least 5% above median: **34.21%**.

For a fixed winning £1 stake, the profit component `(odds - 1)` was about **6.79% higher on average** at the best sportsbook quote than at the median quote (median approximately **6.43%**). This is a secondary explanatory measure; the primary audit uses the more conservative gross-return and break-even comparisons.

## By outcome

Mean best-versus-median gross-return uplift:

- Home: **+3.1312%**,
- Draw: **+4.7348%**,
- Away: **+5.2603%**.

Longer-priced outcomes therefore showed greater quote dispersion in this small sample.

A post-hoc descriptive price-band view reinforces that pattern:

- median odds 1.00–1.99: 23 observations, mean uplift **+2.3057%**,
- 2.00–2.99: 21 observations, **+3.4461%**,
- 3.00–4.99: 57 observations, **+4.2934%**,
- 5.00 and above: 13 observations, **+9.8981%**.

These bands were inspected after seeing the first result and are descriptive only. They must not become thresholds or a reason to prefer longshots.

## Practical account burden

A greedy set-cover diagnostic asks how many sportsbooks in this particular archived sample would have been required to have access to *a tied-best quote* on a given fraction of the 114 outcome observations.

Result:

- 2 sportsbooks: **57.89%** of observations covered at a tied-best price,
- 4 sportsbooks: **82.46%**,
- 6 sportsbooks: **92.98%**,
- 7 sportsbooks: **95.61%**,
- 10 sportsbooks: **100%**.

This is more encouraging than the naive assumption that a user needs every bookmaker account. However, it is only two snapshots of 19 fixtures. The identity of the useful bookmakers can change, account availability differs by user, and exact-best coverage is a stricter standard than simply getting a price close to best.

The next useful practical question is therefore a **price-access frontier**: with 1, 2, 3, 4, 6... bookmaker accounts, how much of the *economic value* of the full best-price universe is retained even when the exact best quote is missed?

## Interpretation

This first result makes best-price comparison a serious product capability rather than decoration.

It does **not** show predictive edge. It shows that, conditional on wanting the same outcome, the market often offers materially different prices at the same moment.

That makes price shopping unusually attractive for Football 1 because it can improve economics without:

- changing the probability model,
- tuning a threshold,
- increasing betting frequency,
- or pretending to know more about football.

A future user-facing contract should continue to separate:

1. Football 1 fair odds,
2. de-vigged market consensus,
3. the user's entered odds,
4. best observed sportsbook odds,
5. bookmaker and quote timestamp,
6. number of eligible books checked.

## Governance

- Decision weight remains 0.
- Best price must never change Football 1 probability.
- Affiliate or sponsorship status must never affect ordering.
- The historical B365 backtest remains untouched; no retrospective multi-book prices are invented.
- Raw exchange prices are not used as directly comparable best prices until commission can be handled honestly.
- Price-shopping gains do not validate a selection policy.
- `Find best price` remains a neutral price-comparison action and never places a bet.
