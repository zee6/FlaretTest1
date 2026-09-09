# Football 1 — Prospective Draw Possibility Lock

**Lock date:** 9 September 2026  
**Decision weight:** 0  
**Primary Football 1 probabilities:** unchanged  
**Source slate:** original immutable 4 September prospective prediction ledger

## Purpose

Freeze the historical Draw Possibility clue before the 12–14 September EPL fixtures are played.

The shadow does not make Draw the H/D/A argmax. It records a separate match-shape ranking based on how evenly the market splits Home and Away win probability.

## Definition

For each fixture:

`H/A gap = abs(market P(Home) - market P(Away))`

The `Draw Possibility` score is a 0–100 historical balance percentile:

- higher = more evenly matched than a larger share of the frozen historical EPL market shapes,
- 100 does **not** mean 100% draw probability,
- the score is not used for fair odds,
- the score has zero decision weight.

The three historical sensitivity flags are all retained:

- within 2 percentage points,
- within 5 percentage points,
- within 10 percentage points.

No one threshold is promoted from the historical result.

## Immutable prospective lock

Model ID:

`draw_possibility_market_balance_percentile_v1`

GitHub Actions run:

`34345280458`

Lock time:

`2026-09-09T11:23:43Z`

Artifact:

- name: `epl-prospective-draw-possibility-shadow`
- artifact ID: `10101426769`
- artifact ZIP digest: `sha256:88f9afc81eef46d375cfd0d1d8efdf7a156f73e6214082f640bc0ae695d16300`
- uncompressed JSONL SHA256: `915b174364b631db6fcdfb6e675855dcf527ec18e214daea701ee7d7d6db17ed`
- records: 10
- historical reference matches: 5,340
- already-started source records excluded: 10

Every record references the original prediction record ID and content hash.

## Frozen 12–14 September ranking

| Rank | Fixture | H/A gap | Draw Possibility | Market pDraw | Fixed balance flags |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | Bournemouth v Brentford | **0.12pp** | **99.21** | 26.65% | ≤2pp, ≤5pp, ≤10pp |
| 2 | Leeds v Newcastle | **2.77pp** | **95.02** | 26.82% | ≤5pp, ≤10pp |
| 3 | Manchester United v Manchester City | 13.65pp | 75.43 | 24.51% | none |
| 4 | Tottenham v Everton | 21.74pp | 61.65 | 26.97% | none |
| 5 | Aston Villa v Nottingham Forest | 22.50pp | 59.93 | 26.32% | none |
| 6 | Crystal Palace v Ipswich | 25.68pp | 55.30 | 26.39% | none |
| 7 | Coventry v Brighton | 27.12pp | 53.20 | 24.53% | none |
| 8 | Sunderland v Arsenal | 48.91pp | 24.46 | 23.07% | none |
| 9 | Liverpool v Fulham | 49.21pp | 24.16 | 19.78% | none |
| 10 | Chelsea v Hull | 67.83pp | 7.68 | 15.20% | none |

## What will be tested

After the ten matches settle, preserve the complete slate and report:

1. realized draws by continuous Draw Possibility rank,
2. outcomes of every predeclared ≤2pp / ≤5pp / ≤10pp flag,
3. realized draw frequency versus the frozen market pDraw,
4. draw-price economics using only price data that was actually recorded before kickoff,
5. no hindsight removal of losing fixtures.

One ten-match slate cannot validate the historical effect. It is the first untouched forward observation after the historical clue was identified.

## Governance

- No Draw probability adjustment.
- No new Football 1 fair odds.
- No betting rule or stake rule.
- No threshold selected from the historical +4–5% aggregate ROI.
- Do not call `99.21` a 99.21% chance of a draw.
- Do not tune Draw Possibility after seeing 12–14 September results.
- Negative prospective results must be preserved.
