# Football 1 — Prospective Evidence Register

**Status:** research governance / read-only evidence map  
**Decision weight:** 0  
**Purpose:** keep Football 1's growing prospective research legible without combining unlike evidence into a misleading master score.

## Why this exists

Football 1 now has several different kinds of prospective evidence running at once. They do not answer the same question and they must not be collapsed into a single confidence number.

The register therefore answers four questions for every live experiment:

1. **What is frozen?**
2. **What metric will judge it?**
3. **What stage is the evidence at?**
4. **What decisions are prohibited?**

This is an evidence map, not another model.

## Evidence lanes

### 1. Primary probability lane

**Question:** Does the frozen Football 1 market-anchored probability estimate outperform the recorded live market consensus prospectively?

**Frozen object:** immutable prediction ledger records.

**Primary judging metrics:** multiclass log loss and Brier score on the same settled fixtures. Accuracy is secondary.

**Current interpretation:** the historical retained residual did not beat the market overall. Prospective observations may confirm, contradict or refine that conclusion, but a small batch cannot promote a betting threshold or model weight.

**Prohibited:** hindsight threshold selection, model-weight changes from one batch, treating raw positive EV as a validated betting rule.

### 2. General recency lane

**Question:** Does weighting recent general form more heavily help the market-anchored model prospectively?

**Frozen objects:** separate 30-day and 15-day recency shadows over the same 12–14 September 2026 event set.

**Primary judging metrics:** multiclass log loss and Brier score on the strict common settled sample, compared with both the market consensus and the original equal-weight Football 1 probability.

**Governance:** the 30-day shadow was frozen first. The 15-day candidate was chosen after inspected historical recency probes and is therefore explicitly post-hoc historically. Both have decision weight zero.

**Prohibited:** replacing the 30-day shadow retrospectively, choosing a half-life from one 10-match batch, stake changes, probability activation.

### 3. Draw Possibility lane

**Question:** Can market H/A balance identify draw-prone match structure that is useful as a ranking/visibility clue even though it has not earned the right to alter draw probability?

**Frozen object:** the exact 12–14 September Draw Possibility shadow, including the continuous balance rank and the original fixed 2pp / 5pp / 10pp balance flags.

**Judging metrics:** ranking/discrimination and fully-settled predeclared group summaries. This lane is not scored as a probability model.

**Historical status:** the balance clue is coherent but post-hoc. A harder probability test failed to improve Brier/log loss, and the historical excess-draw uncertainty audit did not survive the three-probe correction strongly enough for promotion.

**Prohibited:** draw-probability override, betting threshold, stake rule, confidence claim, treating the 0–100 research rank as a probability.

**Future UI guardrail:** the internal 0–100 rank is mathematically useful but visually dangerous. At first glance it can resemble a 99% probability, confidence score or strong betting recommendation. The eventual interface must convey structural match shape simply without looking like a “nap” or recommendation. **No UI change is required now; preserve the research score until later product work.**

### 4. Movement lane

**Question:** Can a frozen timing forecast improve price execution relative to acting immediately, once a genuinely comparable later market snapshot exists?

**Frozen object:** immutable prospective movement records plus timestamped odds snapshots.

**Judging metrics:** movement error/direction on common-bookmaker comparisons and, more importantly, eventual obtainable-price improvement including the cost of waiting when value disappears.

**Historical status:** the earlier residual did not predict closing movement. The prospective movement suite therefore remains a zero-weight execution experiment, not evidence that Football 1 predicts market direction.

**Prohibited:** ACT NOW / WAIT product activation without prospective support, retrospective snapshot choice, using bookmaker-composition changes as market movement.

### 5. Portfolio lane

**Question:** What happens to capital under predeclared risk controls and descriptive shadow selections?

**Frozen policy:** the official research portfolio places zero compulsory bets while no selection rule is prospectively validated. Shadow portfolios are counterfactual observers only.

**Judging metrics:** bankroll path, turnover, ROI, drawdown, losing streak and exposure. These describe capital consequences; they do not validate football probabilities by themselves.

**Historical status:** drawdown controls reduced capital damage but did not create edge.

**Prohibited:** feeding portfolio losses back into match probabilities, loss chasing, promoting a shadow strategy because it wins one matchweek, conviction-upside activation without separate validation.

## No master score

The register MUST NOT calculate a combined “Football 1 confidence” or weighted average across these lanes.

A lower log loss, a good Draw Possibility rank, correct market movement and a shallower portfolio drawdown are different observations about different objects. Combining them numerically would create false precision and could accidentally turn descriptive evidence into a recommendation engine.

## Evidence stages

The machine-readable register uses a small vocabulary:

- `historical_observed` — already inspected historical evidence;
- `prospective_frozen` — method/object locked before the relevant future outcome;
- `prospective_partial` — some relevant outcomes observed but the predeclared batch is incomplete;
- `prospective_complete` — the predeclared batch is fully observed and can be scored without redefining it;
- `not_eligible_for_promotion` — evidence is descriptive/post-hoc or otherwise cannot by itself activate product decision weight.

A stage describes research chronology. It does **not** imply that the result is good.

## Core rule

> **Evidence may move between stages. Definitions do not move after the result.**

The same register code should be rerun after the 12–14 September fixtures settle. The new information should be the observed evidence, not a rewritten judging rule.
