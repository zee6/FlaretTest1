# October prospective partial results — 11 October 2026

**Stage: 5 of 9 recorded forecasts settled; 4 unresolved.** This is an interim report, not a complete-slate conclusion. The original predictions, features, model settings, quoted odds, October manifest and recency shadows are unchanged. Arsenal–Leeds remains excluded because it had started before our snapshot.

## Verified results and probability quality

The five 10 October results were checked against published final scores from The Guardian and SuperSport, with a further cross-check against the structured EPL results tool. Settlement provenance records the actual verification time, `2026-10-11T12:58:18.945134+00:00`. The results are manually verified public-source transcriptions, not an Odds API scores response; the event IDs are linked from the original frozen predictions.

| Fixture | Final score | Market probability of actual outcome | Primary model probability of actual outcome |
|---|---:|---:|---:|
| Aston Villa–Brentford | 2–2 | 26.7773% | 26.4400% |
| Chelsea–Bournemouth | 5–1 | 52.7878% | 49.6329% |
| Ipswich Town–Fulham | 2–1 | 34.4964% | 32.9803% |
| Sunderland–Brighton | 0–2 | 41.4989% | 40.3356% |
| Manchester United–Tottenham | 1–1 | 23.0299% | 22.9196% |

All five primary residual adjustments moved away from the realized outcome. This is descriptive evidence from a small partial sample; it is not a reason to invert or refit the model after seeing the results.

Sources:

- [The Guardian: four afternoon full-time results](https://www.theguardian.com/football/live/2026/oct/10/chelsea-v-bournemouth-sunderland-v-brighton-and-more-football-live)
- [The Guardian: Manchester United–Tottenham full time](https://www.theguardian.com/football/live/2026/oct/10/manchester-united-v-tottenham-premier-league-live)
- [SuperSport: Premier League completed results](https://supersport.com/football/tour/c0ca5665-d9d9-42dc-ad86-a7f48a4da2c6/results)

The same five settled events are used for every probability comparison:

| Model | Mean log loss | Mean Brier score | Log-loss difference versus market |
|---|---:|---:|---:|
| Recorded market consensus | 1.073740 | 0.649354 | 0.000000 |
| Original primary model | 1.104236 | 0.671819 | +0.030496 |
| 15-day recency shadow | 1.094125 | 0.664178 | +0.020385 |
| 30-day recency shadow | 1.104998 | 0.672329 | +0.031258 |

Lower is better. Each candidate trails the market on both metrics. No candidate is activated, no probability is overridden, and no threshold or half-life is changed. October Draw Possibility remains unavailable; the newly recovered September Draw file does not substitute for it.

## Accounting and sanity checks

**Official portfolio: zero bets, zero staked, zero realized P&L.**

For the existing descriptive diagnostic that selects the largest recorded model EV in every settled match, using exactly one unit per match:

| Fixture | Recorded max-EV choice | Recorded decimal odds | Unit P&L | Cumulative units |
|---|---|---:|---:|---:|
| Aston Villa–Brentford | Brentford | 2.60 | −1.00 | −1.00 |
| Ipswich Town–Fulham | Fulham | 2.58 | −1.00 | −2.00 |
| Sunderland–Brighton | Sunderland | 3.25 | −1.00 | −3.00 |
| Chelsea–Bournemouth | Bournemouth | 4.50 | −1.00 | −4.00 |
| Manchester United–Tottenham | Manchester United | 1.79 | −1.00 | −5.00 |

This hypothetical diagnostic has 0 winners / 5 losers, 5 units staked, −5 units P&L, −100% ROI and 5 units maximum drawdown from a zero starting P&L. The four simultaneous afternoon matches are displayed in ledger order; there is no implied intraday reinvestment. These are accounting units, not money wagered, and not an activated selection rule.

For each frozen choice, EV is `p_model * decimal_odds - 1`. Net one-unit P&L is `decimal_odds - 1` for a winning choice and `-1` for a losing choice. For example, Villa–Brentford finished as a draw: the frozen Brentford selection loses one unit despite its quoted 2.60 price. A 2.60 win would return 2.60 gross, hence 1.60 net, but that did not occur.

The scorer recomputes log loss as `-ln(p_actual)` and Brier as the sum of squared H/D/A probability errors. All five stored results, scores, EV selections and all 15 hypothetical outcome P&Ls were checked against the original inputs. The prediction ledger SHA-256 remains `6194c719320129357dd8f69e1acde21d652f7f7493c811aff5a17ad50e7ceed3`. The settlement file retains its previous bytes and appends exactly five records, taking the full project to 39 predictions / 35 settlements / 4 unresolved.

Unresolved in this report: Hull–Everton, Crystal Palace–Nottingham Forest, Liverpool–Manchester City and Coventry–Newcastle. Append only independently verified completed results, then rerun:

```bash
python -m football1.october_slate_report --output /tmp/october-slate-report.json
```
