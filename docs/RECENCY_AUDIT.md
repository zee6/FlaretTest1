# Football 1 Recency-Weighted Form Audit v1

**Status date:** 7 September 2026  
**Status:** historical exploratory research on previously inspected data  
**Decision weight:** 0.0  
**Promotion allowed:** no

## Purpose

This audit tests the user hypothesis that recent football results and performances should matter more than older results because team form, confidence and tactical state evolve over time.

The experiment deliberately changes only the weighting of Football 1's existing last-5 / last-10 form summaries. It does **not** change the market anchor, feature count, Elo calculation, rest features, prior-game features, residual architecture, regularization, chronological split policy or same-day leakage protection.

## Existing recency before this audit

Football 1 already contains some time sensitivity, but not in the main last-5 / last-10 feature summaries:

- Dixon-Coles uses exponential match-age weighting with `TIME_DECAY_PER_DAY = 0.0020`, equivalent to a half-life of about 347 days.
- Davidson uses `TIME_DECAY_PER_DAY = 0.0015`, equivalent to about 462 days.
- Elo updates sequentially and regresses 25% of rating deviation toward 1500 at a new season, but does not decay solely because days pass within a season.
- The ordinary Football 1 form features use the last 5 and last 10 matches with equal weight inside each window.

Thus a match played last weekend and one several weeks earlier previously contributed equally if both remained inside the same form window.

## Experimental design

Control:

- existing equal-weight last-5 / last-10 summaries.

Predeclared sensitivity probes:

- 30-day exponential half-life;
- 60-day exponential half-life;
- 120-day exponential half-life.

For a past match aged `d` days, weight is:

`exp(-ln(2) * d / half_life_days)`

The neutral prior smoothing remains unchanged.

All variants were required to align match-for-match and in identical order with the equal-weight control. The audit aborts rather than compare different samples.

Evaluation used the existing fixed-market offset football residual with alpha 0.10, walk-forward by season, on the frozen 4 September canonical database.

## Reproducibility

PR #45: `Research recency-weighted form audit v1`  
Merged to master at commit `d13600d14c4db931657922ed9763892acd790fb0`.

PR recency workflow:

- run `34165561801`
- job `101875787551`
- conclusion: success
- tests: **203 passed**
- artifact: `epl-recency-audit`, ID `10034027044`

Frozen source:

- audit run `33924106948`
- source head `ada0ebe987323389870d80aca0234be11c18b53d`
- database SHA-256 `4b5c751b22608026fb18eb190279c13b41d50ab88055057787c041ae4b841454`

## Overall results — 4,200 OOS matches

| Model | Log loss | Δ LL vs equal control | Brier | Δ Brier vs equal control | Accuracy | Top-label ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| De-vig B365 market | **0.960279** | — | **0.569005** | — | **54.88%** | 0.020085 |
| Equal-weight Football 1 control | 0.962730 | 0 | 0.570342 | 0 | 54.55% | **0.014971** |
| Recency 120d | 0.962628 | -0.000102 | 0.570280 | -0.000062 | 54.52% | 0.015299 |
| Recency 60d | 0.962524 | -0.000206 | 0.570230 | -0.000112 | 54.52% | 0.015040 |
| Recency 30d | **0.962397** | **-0.000333** | **0.570171** | **-0.000170** | 54.45% | 0.017577 |

Lower log loss, Brier and ECE are better.

All three recency variants improved log loss and Brier slightly relative to the equal-weight Football 1 control. The fastest 30-day probe produced the largest improvement on those two metrics.

However:

1. every Football 1 variant remained worse than the de-vigged market in log loss and Brier;
2. the 30-day variant reduced classification accuracy slightly;
3. its globally measured top-label calibration error was worse than the equal-weight control;
4. the magnitude of improvement is small.

## Season stability

For the 30-day probe, log loss improved relative to equal weighting in **8 of 12 held-out seasons**.

The improvement was not created solely by the small 2026/27 sample. Excluding the 20-match 2026/27 test season, its weighted log-loss improvement versus equal weighting remained about **-0.000301** over 4,180 matches.

By season, the 30-day log-loss delta versus the equal-weight control was approximately:

- 2015/16: -0.00268
- 2016/17: -0.00228
- 2017/18: +0.00105
- 2018/19: +0.00058
- 2019/20: -0.00051
- 2020/21: -0.00098
- 2021/22: -0.00012
- 2022/23: -0.00012
- 2023/24: +0.00206
- 2024/25: -0.00093
- 2025/26: +0.00063
- 2026/27 (20 matches): -0.00701

This is more encouraging than a gain concentrated in one historical period, but is not sufficiently strong or fresh to validate 30 days as an optimal half-life.

## Interpretation

The audit supports a narrow statement:

> **Giving recent form more weight is a plausible research direction and slightly improved the existing Football 1 residual historically.**

It does **not** support:

> **30 days is the correct decay rate**, or **recency now beats the bookmaker market**.

The 30/60/120-day values were all observed on already-inspected history. Choosing 30 days because it ranked first would be retrospective model selection. It therefore remains a zero-weight research lead unless a decay policy is frozen before untouched prospective evaluation.

The result is nevertheless useful because the three probes show a monotonic aggregate pattern in log loss/Brier: faster decay produced larger improvement over equal weighting. That is evidence worth preserving, but not enough to promote.

## Possible next research

Without tuning these historical results, sensible next work includes:

- define a recency policy prospectively before new fixtures accumulate;
- test whether the effect is stronger in identifiable regime-change situations rather than every match;
- examine manager changes, promotion, injuries and tactical shifts as explicit state-change signals;
- compare recent-5 performance with the preceding-5 as a zero-weight 'momentum / regime-change' observer;
- separately audit faster/slower decay inside Dixon-Coles rather than assuming its current ~347-day half-life is optimal;
- keep portfolio P&L completely separate from football probability recency.

No recency variant is activated in Football 1 fair probabilities or the Swift interface by this audit.
