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

## Practical account burden — exact best

A greedy set-cover diagnostic asks how many sportsbooks in this particular archived sample would have been required to have access to *a tied-best quote* on a given fraction of the 114 outcome observations.

Result:

- 2 sportsbooks: **57.89%** of observations covered at a tied-best price,
- 4 sportsbooks: **82.46%**,
- 6 sportsbooks: **92.98%**,
- 7 sportsbooks: **95.61%**,
- 10 sportsbooks: **100%**.

This is more encouraging than the naive assumption that a user needs every bookmaker account. However, exact-best coverage is a strict standard; missing the exact leader by a trivial amount may have little economic cost.

## Practical account burden — price-access frontier

`src/football1/price_access_frontier.py` therefore asks a more useful question: as sportsbook-account access increases, how close is the best quote available from that restricted set to the full 18-sportsbook best quote?

The account set is chosen greedily on this already observed sample to maximize coverage and price closeness. It is a **post-hoc diagnostic**, not a recommendation about which bookmaker accounts anybody should hold.

Result:

| Accounts | Exact best | Within 1% of full best | Within 2% | Mean price shortfall vs full best | Mean winning-profit shortfall |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 40.35% | 44.74% | 59.65% | 2.2295% | 3.2366% |
| 2 | 57.89% | 62.28% | 77.19% | 1.3237% | 1.9119% |
| 3 | 74.56% | 80.70% | 85.96% | 0.7393% | 0.9632% |
| 4 | 82.46% | 88.60% | 92.11% | 0.4056% | 0.5527% |
| 5 | 89.47% | 93.86% | 95.61% | 0.2033% | 0.3021% |
| 6 | 92.11% | 96.49% | 98.25% | 0.1245% | 0.1892% |
| 8 | 95.61% | 100.00% | 100.00% | 0.0255% | 0.0657% |
| 10 | 100.00% | 100.00% | 100.00% | 0.0000% | 0.0000% |

The important practical observation is that **near-best access is much more concentrated than exact-best access**. In this first sample, four accounts left the available quote only about 0.41% below the full-universe best on average; six reduced that to about 0.12%.

This is promising for the product concept because `Find best price` need not imply that a rational user must maintain every bookmaker account. A future Bet Check can also compare the user's entered quote directly with the full observed best and say, for example, that the user's price is already within 1% of best.

These figures must be accumulated over many more prospective snapshots before any bookmaker-set claim is considered stable.

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

A useful Bet Check interpretation layer can additionally state whether the user's entered price is exact best, within 1% of best, within 2%, or materially worse. Those labels describe **price quality only** and must not be confused with confidence in the football outcome.

## Governance

- Decision weight remains 0.
- Best price must never change Football 1 probability.
- Affiliate or sponsorship status must never affect ordering.
- The historical B365 backtest remains untouched; no retrospective multi-book prices are invented.
- Raw exchange prices are not used as directly comparable best prices until commission can be handled honestly.
- Price-shopping gains do not validate a selection policy.
- `Find best price` remains a neutral price-comparison action and never places a bet.
- The greedy account frontier is not a bookmaker recommendation and must not be monetized through reordered affiliate placement.
