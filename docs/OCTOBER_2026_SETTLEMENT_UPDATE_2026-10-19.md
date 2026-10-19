# October prospective settlement update — 19 October 2026

Verified at **2026-10-19T18:53:17.884810+00:00**. Development: Godo and Dave.

## Recorded outcomes and scope

Thirteen independently checked final scores were appended: the four outstanding 11–12 October results and nine completed 17–18 October matches. The ledger now holds **59 original predictions, 48 settlements and 11 unresolved records**. Original prediction, movement and odds files are unchanged; all original 35 settlement lines remain an identical prefix.

The 10–12 October comparison is complete at **9/9**. The 17–19 October comparison is **9/10**, with Tottenham–Coventry still unresolved at verification. The ten already locked 23–25 October forecasts are excluded from both comparisons. Arsenal–Leeds on 10 October remains excluded because it started before that slate's snapshot; no prediction was reconstructed.

Published final scores were cross-checked between [Football Web Pages](https://www.footballwebpages.co.uk/premier-league/fixtures-results), the [NBC schedule/results](https://www.nbcsports.com/soccer/news/premier-league-schedule-for-2026-27-season-released) and the structured EPL results feed. The source-controlled [verification record](../prospective/verified_results/2026-10-19.json) preserves scores, original prediction IDs/hashes, source URLs and verification time. Each appended settlement also carries this provenance. These are manually transcribed published finals, not a fetched Odds API score payload; no provider update time is inferred.

## Identical-sample probability comparison

Lower log loss and Brier are better. Each row uses the same settled original IDs within its slate. Accuracy is the secondary, most-likely-outcome measure; it is different from the price-based max-EV diagnostic below.

| Frozen slate | Forecast | Mean log loss | Mean Brier | Argmax accuracy |
|---|---|---:|---:|---:|
| 10–12 Oct (9/9) | Market consensus | 1.087786 | 0.661501 | 33.3% |
| 10–12 Oct (9/9) | Football 1 primary | 1.108346 | 0.677205 | 33.3% |
| 10–12 Oct (9/9) | 15-day recency shadow | 1.103207 | 0.673232 | 33.3% |
| 10–12 Oct (9/9) | 30-day recency shadow | 1.110975 | 0.679037 | 33.3% |
| 17–19 Oct (9/10) | Market consensus | 0.784034 | 0.442921 | 66.7% |
| 17–19 Oct (9/10) | Football 1 primary | 0.778606 | 0.438626 | 66.7% |
| 17–19 Oct (9/10) | 15-day recency shadow | 0.782153 | 0.441495 | 66.7% |
| 17–19 Oct (9/10) | 30-day recency shadow | 0.780429 | 0.440047 | 66.7% |

Football 1 trails the market on the complete earlier slate: log loss delta **+0.020560**, Brier delta **+0.015704**. Both recency shadows also trail the market there. The [five-match interim negative finding](OCTOBER_2026_PARTIAL_RESULTS.md) remains a dated part of the record.

On the nine completed matches this weekend, Football 1 is slightly better: log loss delta **−0.005428**, Brier delta **−0.004295**. Both recency shadows also improve slightly on the market, with the primary ahead of either shadow. These small batches do not establish an overall edge or select a winning model. The retained model specification, alpha=0.10 and all observer decision weights are unchanged. Draw Possibility remains unavailable because its original fixed September reference database is missing; no replacement is supplied after results.

## One-unit diagnostic and arithmetic

This is the existing hypothetical observer: one unit on the original recorded maximum-EV outcome in every settled match, including negative-EV selections. It uses the quoted best decimal price at the original snapshot, with gross returns and no execution, availability or commission assumption. It is not an approved betting policy. Official bets, stake and P&L remain **zero**; official ROI is unavailable because turnover is zero.

| Frozen slate | Settled stakes | Wins / losses | P&L, units | ROI on stake | Maximum drawdown, units |
|---|---:|---:|---:|---:|---:|
| 10–12 Oct | 9 | 1 / 8 | −5.60 | −62.22% | 8.00 |
| 17–19 Oct, partial | 9 | 4 / 5 | +0.92 | +10.22% | 1.80 |

The arithmetic is `EV = frozen model probability × decimal odds − 1`; a winning unit returns `odds − 1` profit and a losing unit returns `−1`. ROI is net P&L divided by settled stake. The old slate has eight losses and Coventry at 3.40 winning: `−8 + 2.40 = −5.60`; `−5.60 / 9 = −62.22%`. This weekend's four winners returned `1.98 + 0.69 + 2.05 + 1.20 = 5.92` profit; five losses give `5.92 − 5 = +0.92`, or `0.92 / 9 = +10.22%`.

Drawdown starts from zero diagnostic equity, tracks the running peak and groups simultaneous kickoffs before updating equity. Weekend grouped equity is `−1.00, +0.67, +2.72, +1.92, +0.92`; the largest drop from the peak is **1.80**. In the earlier slate, equity reaches **−8.00** before Coventry's winner. No unresolved match contributes a stake, result, zero score or ROI.

| Date | Fixture | Final | Recorded max-EV selection | Frozen decimal price | P&L, units |
|---|---|---|---|---:|---:|
| 2026-10-10 | Aston Villa – Brentford | 2–2 | Brentford | 2.60 | -1.00 |
| 2026-10-10 | Ipswich Town – Fulham | 2–1 | Fulham | 2.58 | -1.00 |
| 2026-10-10 | Sunderland – Brighton and Hove Albion | 0–2 | Sunderland | 3.25 | -1.00 |
| 2026-10-10 | Chelsea – Bournemouth | 5–1 | Bournemouth | 4.50 | -1.00 |
| 2026-10-10 | Manchester United – Tottenham Hotspur | 1–1 | Manchester United | 1.79 | -1.00 |
| 2026-10-11 | Crystal Palace – Nottingham Forest | 3–1 | Nottingham Forest | 2.70 | -1.00 |
| 2026-10-11 | Hull City – Everton | 2–2 | Everton | 2.20 | -1.00 |
| 2026-10-11 | Liverpool – Manchester City | 0–3 | Liverpool | 3.10 | -1.00 |
| 2026-10-12 | Coventry City – Newcastle United | 4–1 | Coventry City | 3.40 | +2.40 |
| 2026-10-17 | Everton – Chelsea | 0–2 | Everton | 3.10 | -1.00 |
| 2026-10-17 | Manchester City – Ipswich Town | 3–2 | Ipswich Town | 14.00 | -1.00 |
| 2026-10-17 | Brentford – Liverpool | 1–2 | Liverpool | 2.98 | +1.98 |
| 2026-10-17 | Fulham – Hull City | 1–0 | Fulham | 1.69 | +0.69 |
| 2026-10-17 | Newcastle United – Aston Villa | 0–1 | Aston Villa | 3.05 | +2.05 |
| 2026-10-18 | Bournemouth – Sunderland | 2–0 | Bournemouth | 2.20 | +1.20 |
| 2026-10-18 | Leeds United – Manchester United | 1–1 | Manchester United | 3.05 | -1.00 |
| 2026-10-18 | Brighton and Hove Albion – Crystal Palace | 5–0 | Crystal Palace | 6.40 | -1.00 |
| 2026-10-18 | Nottingham Forest – Arsenal | 0–1 | Nottingham Forest | 6.20 | -1.00 |

Fulham's winning selection had slightly negative forecast EV (−0.000368). Retaining it is intentional: removing it after the result would change this every-match diagnostic. The same rule retains the earlier Manchester United negative-EV loss.

## Reproduction and validation

```bash
PYTHONPATH=src python -m football1.october_slate_report --output /tmp/october10-report.json
PYTHONPATH=src python -m football1.october_slate_report --slate 2026-10-17-19 --output /tmp/october17-report.json
PYTHONPATH=src python -m football1.mobile_results --check
PYTHONPATH=src python -m pytest -q
```

The default evaluator still selects the original nine-match 10–12 October manifest. The new explicit slate option pins the ten-match 17–19 October manifest and its original hashes. It verifies source identities, pre-kickoff locks, semantic settlement correctness and shared scorer counts before evaluation. The two dedicated CI workflows retain their report artifacts for 90 days. The committed ledgers, frozen shadows and dated provenance permit offline reproduction after those artifacts expire.

Local validation: **345 Python tests passed**. The expanded slate tests exercise both manifests, reject altered or rehashed corrupt evidence and exclude later snapshots/next-week fixtures. A separate hand-calculated unit-accounting case checks wins, losses, negative-EV inclusion, unsettled exclusion, ROI and grouped drawdown. App feed totals, probability scores, P&L and drawdown agree with the reports. The feed freshness check, all workflow YAML parsing and diff whitespace checks passed.

The iPhone Results feed is refreshed. Its newest batch still spans **17–25 October**, because batches follow snapshot time; it now shows **9 settled / 11 pending**. The dated research comparison remains only this weekend's ten fixtures. No model inference, new betting strategy, threshold selection or native interface change is introduced by this settlement update. See [the current checkpoint](RESUME_CHECKPOINT.md) for the next action.
