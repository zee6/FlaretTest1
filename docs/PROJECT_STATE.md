# Football 1 — Maintained Project State

**Status date:** 7 September 2026  
**Development credit:** Godo and Dave  
**Repository:** `zee6/FlaretTest1`

This document is the maintained status map for Football 1. It consolidates the existing implementation, earlier research decisions, and the additional product/research decisions agreed on 7 September 2026.

It is **additive**, not a replacement for earlier frozen research documents such as `PHASE1C_RESULTS.md` and `PROSPECTIVE_PROTOCOL.md`.

The core rule for this document is simple:

> **Implemented research is not the same thing as an approved product feature, and an approved idea is not the same thing as validated predictive edge.**

---

## 1. Product doctrine

Football 1 is an EPL-first football probability, bookmaker-price and mispricing research system intended to become a native Apple-silicon application.

The central economic object is **price, not inference**.

The product should eventually expose four distinct layers:

### Prophet — what do we think will happen?

Give users a clear football opinion: Home / Draw / Away probabilities, likely score structures and model-jury agreement or disagreement.

The Prophet should not be hidden merely because the portfolio layer later rejects a bet. A correct prediction and a correct betting decision are different achievements.

### Trader — is the bookmaker price attractive?

Compare the currently available bookmaker price with our own fair-price estimate.

The interface must always distinguish:

- raw bookmaker implied probability;
- the **margin-free / de-vigged market benchmark**;
- **our independently estimated fair probability**;
- our fair decimal odds derived from that probability.

A de-vigged bookmaker price is a market benchmark. It is **not** automatically “our fair odds.”

### Movement — is the price likely to improve or disappear?

Movement prediction is an execution/timing layer, not a substitute for valuation.

The eventual language should be explicit and testable:

- value + predicted shortening → possible **ACT NOW** candidate;
- value + predicted drift → possible **WAIT**;
- no value yet + predicted drift into value → **WATCH**;
- strong model/market conflict → **HOLD / INVESTIGATE**;
- no sufficient edge → **PASS**.

These are research concepts, not active betting rules, until thresholds have been selected without hindsight and survived untouched prospective testing.

### Portfolio — should this trade exist at all?

The portfolio layer should decide whether an otherwise interesting price belongs in the user’s set of positions, taking account of exposure, concentration, correlation and risk.

A favourite can be our most likely winner and still be a correct **PASS** at an unattractive price.

---

## 2. Non-negotiable research rules

These rules remain in force across every model and product layer.

### No leakage

A prediction may use only information genuinely available at its decision timestamp.

No result, later bookmaker quote, later lineup, later injury report, revised statistic or hindsight-derived label may leak backwards into an earlier decision.

### Time splits only

Predictive evaluation must use chronological / walk-forward validation. Do not use random train/test splits for claims of future performance.

### Timestamp integrity

Raw odds and derived probabilities must remain separate. Retrieval timestamps and kickoff semantics must remain explicit. Closing prices must never be treated as if they were available earlier.

### Preserve negative findings

Negative empirical results are part of the research record. Do not tune them away.

In particular:

> **The retained alpha=0.10 fixed-market residual model has not beaten the market overall.**

It remains useful as a safe market-anchored architecture and research object, but it must not be presented as an overall proven edge.

### Previously inspected results are not fresh confirmation

Phase 1C and other previously viewed OOS results have already been inspected. They cannot later be relabelled as untouched confirmation for a new rule chosen after inspection.

### New jurors start with zero decision weight

Interesting models may be logged and scored prospectively with zero product/trading weight. A model earns influence only through pre-specified, honest, time-ordered evidence.

### No one-snapshot strategy creation

Do not create, optimize or promote a betting rule from one attractive observation or a small number of prospective examples.

---

## 3. Verified implemented research components

The following components are present in the repository as code, tests, workflows and/or frozen research artefacts. “Implemented” here means the research implementation exists; it does **not** mean it has earned product weight or economic value.

### Historical data and audit pipeline — IMPLEMENTED

Current code includes:

- Football-Data.co.uk ingestion;
- immutable/raw-data handling conventions;
- schema/canonical database construction;
- audit tooling;
- leakage-safe feature construction;
- market-baseline scoring;
- walk-forward probability evaluation;
- mispricing backtests.

Phase 1C remains the frozen benchmark. The documented broad football-only model, unconstrained market slant and fixed-market residual all failed to beat the de-vigged Bet365 benchmark overall.

### Market baseline and fixed-market residual architecture — IMPLEMENTED / RETAINED

The preferred historical probability architecture remains market anchored:

- begin from de-vigged market probabilities;
- learn only a small residual football-information adjustment;
- zero residual adjustment reproduces the market exactly.

The current alpha=0.10 residual result is negative overall and must remain labelled that way.

### Random-forest residual — IMPLEMENTED RESEARCH, ZERO LIVE WEIGHT

`src/football1/random_forest_residual.py` implements a market-aware `RandomForestClassifier` with frozen conservative hyperparameters and a fixed 0.10 geometric/log-probability interpolation from market toward the RF candidate.

Its evaluation is walk-forward by season, with same-day leakage protection.

The implementation records descriptive feature importance for the latest training block, with an explicit warning that impurity importance is **not** OOS proof of feature value.

**Important product gap:** reliable user-facing explanation is not yet complete. Global impurity importance is not a sufficient per-prediction explanation layer. Future explanation work must be faithful to the fitted RF and validated rather than generated as post-hoc storytelling.

### Elo / dynamic strength — IMPLEMENTED RESEARCH

The repository includes:

- `elo.py`;
- `elo_research.py`;
- `elo_ablation.py`;
- `elo_observer.py`;
- tests and GitHub workflows;
- published `research/elo_research.json`;
- an iPhone-side `EloResearch.swift` implementation/reference component.

Do not propose a fresh Elo system without first working from these existing implementations and results.

### Bayesian strength — IMPLEMENTED RESEARCH

The repository contains `bayesian_strength.py` plus an ablation implementation, tests and a workflow.

### Home / away specialist — IMPLEMENTED RESEARCH

The repository contains `home_away.py`, an ablation, tests and workflows.

### Head-to-head specialist — IMPLEMENTED RESEARCH

The repository contains `head_to_head.py`, an ablation, tests and workflows.

Any future H2H use must still prove incremental value; the existence of the module is not evidence that H2H is predictive.

### Promotion prior — IMPLEMENTED RESEARCH

The repository contains `promotion_prior.py`, tests and a workflow/audit path for promoted-club priors.

### Scoreline model — IMPLEMENTED RESEARCH

`scoreline.py` builds leakage-safe venue-specific goal histories, estimates expected goals, creates an explicit Poisson score grid, and derives Home / Draw / Away probabilities plus a modal scoreline.

The implementation snapshots an entire calendar date before incorporating any results from that date.

### Dixon–Coles — IMPLEMENTED RESEARCH

`dixon_coles.py` implements a time-weighted attack/defence model with a Dixon–Coles low-score dependence correction, expected goals, scoreline probabilities and H/D/A probabilities. An ablation, tests and workflow are present.

### Davidson draw-aware strength model — IMPLEMENTED RESEARCH

`davidson.py` implements a time-weighted Bradley–Terry–Davidson model with an explicit learned draw factor. It outputs H/D/A probabilities rather than treating draw probability merely as a residual.

### Correlated-score model — IMPLEMENTED RESEARCH

The repository contains `correlated_score.py`, an ablation, tests and workflow.

### Non-transitive / matchup research — IMPLEMENTED RESEARCH

The repository contains `nontransitive.py` as an explicit research avenue for effects that are not captured by a single transitive strength ordering.

### Model disagreement and confidence observers — IMPLEMENTED RESEARCH

The repository includes `model_disagreement.py` and `confidence_observer.py` with tests/workflows. These are useful foundations for the future “jury disagreement” product concept.

### Historical closing-line and movement research — IMPLEMENTED RESEARCH

The repository contains:

- `historical_closing_line.py`;
- `closing_movement_rf.py`;
- `market_consensus_movement.py`;
- `market_consensus_baseline_check.py`;
- `market_movement_observer.py`;
- `market_regime_audit.py`;
- `market_regime_movement.py`;
- `shadow_price_consensus.py`;
- associated tests and workflows.

### Live odds and archive — IMPLEMENTED

The repository contains:

- `live_odds.py`;
- `odds_archive.py`;
- tests;
- live-odds and archive workflows.

Free/inexpensive API usage remains part of the experiment.

### Prospective prediction ledger — IMPLEMENTED

`prospective/ledger.jsonl` is present and the prospective protocol requires immutable pre-kickoff prediction records with timestamps, event identity, market consensus, model identity and content hashes.

Settlement is designed to be separate from prediction creation.

### Prospective movement ledger — IMPLEMENTED, ZERO DECISION WEIGHT

`prospective/movement_predictions.jsonl` is present.

`prospective_consensus_movement.py` explicitly creates locked movement records with:

- `decision_weight: 0.0`;
- no betting rule;
- no movement threshold;
- no staking rule;
- content-hash verification;
- pre-kickoff lock validation;
- common-bookmaker scoring between initial and later snapshots to avoid bookmaker-composition drift.

The frozen movement predictions from 4 September 2026 must not be refit or rewritten.

### Archived bookmaker snapshots — IMPLEMENTED

`prospective/odds_snapshots.jsonl` is present and is used for prospective common-book movement comparison.

### iPhone SwiftUI app target — IMPLEMENTED UI PROTOTYPE, NOT FULL ON-DEVICE INFERENCE

A real Xcode/iOS project exists at `ios/Football1Mobile`.

Current documented boundary:

- native SwiftUI interface;
- preview-labelled values;
- no bookmaker API calls in the iPhone app;
- no language-model dependency;
- Python-generated prospective data is intended to bridge into the UI;
- full model logic has **not** been migrated into Swift/Core ML.

This distinction must remain clear.

### macOS SwiftUI app target — IMPLEMENTED UI PROTOTYPE, NOT FULL ON-DEVICE INFERENCE

A real macOS Xcode target exists at `macos/Football1App` and is CI-built.

Current documented boundary:

- real fixture names and some real market-consensus values from the first successful live snapshot;
- preview Football 1 probabilities for interface work;
- frozen Phase 1C research metrics;
- preview prospective rows;
- Python remains the modelling source of truth.

The current interface direction is considered good and should be preserved rather than redesigned wholesale.

---

## 4. Draw work — current state and next requirement

Draw research is **not starting from zero**. Football 1 already contains several relevant implementations:

- explicit Poisson scoreline probabilities;
- Dixon–Coles low-score dependence;
- Davidson’s explicit draw factor;
- correlated-score modelling;
- market benchmark probabilities;
- model disagreement tooling.

The approved next draw task is therefore a **draw-specific audit and calibration layer across existing models**, not another unexamined model added to the pile.

The audit should answer:

1. Are draw probabilities calibrated?
2. Do high-predicted-draw fixtures actually contain more draws than low-predicted-draw fixtures?
3. Are the models assigning draw probability to the **right matches**?
4. How do 0–0, 1–1, 2–2 and higher-scoring draws contribute?
5. Which existing model handles low-score draw dependence best?
6. Are there identifiable fixture classes where the market or our models systematically misprice draws?
7. Does any draw-specific improvement survive walk-forward testing versus the de-vigged market?

Evaluation should include at minimum:

- multiclass log loss;
- Brier score;
- draw calibration curves/bins;
- draw ranking/discrimination;
- scoreline decomposition;
- market-relative fair-price error;
- economic evaluation only when an actual predeclared pricing rule exists.

Do not judge draw work by draw hit rate alone.

---

## 5. Neural-network requirement

**Status: APPROVED PROPOSAL — NOT YET IMPLEMENTED AS A RESEARCH JUROR**

The repository currently has scikit-learn as its principal ML dependency and contains no dedicated small neural-network research module in the present tree.

Football 1 should investigate at least one **small neural model** suitable for Apple-silicon deployment, but only after the current research jury has been audited.

Possible purposes include:

- nonlinear interactions among leakage-safe features;
- temporal form/regime sequences;
- interactions that tree/logistic models represent poorly.

Constraints:

- EPL-only sample size makes overfitting a major risk;
- architecture size must be justified by the data volume;
- validation remains walk-forward;
- the neural model enters with zero decision weight;
- no neural architecture should be selected because it produces an attractive result on already-inspected data.

The eventual deployment target should be Core ML or another robust Apple-silicon-native path with regression checks against the research implementation.

---

## 6. Random-forest explanation requirement

**Status: RF IMPLEMENTED; PRODUCT-GRADE EXPLANATION PARTIAL / PROPOSED**

The existing RF implementation exposes training-set impurity importance and correctly warns against interpreting it as OOS proof.

Before the RF becomes a visible juror in the app, add explanation machinery that can answer, faithfully and repeatably:

- which current inputs materially shifted this fixture relative to the market anchor;
- in which direction they shifted H/D/A;
- how stable that explanation is across nearby model fits;
- whether the explanation is local to this fixture or merely global feature importance.

Do not let a language model invent the explanation after the prediction.

---

## 7. Fair-price and market-price presentation

**Status: APPROVED CENTRAL PRODUCT REQUIREMENT; UI refinement still required**

The app’s clearest value proposition is comparison of bookmaker prices with fair-price estimates.

For each H/D/A outcome, the system should be able to distinguish:

1. **Quoted decimal odds** — the bookmaker offer.
2. **Raw implied probability** — `1 / decimal_odds`, including margin.
3. **De-vigged market benchmark** — consensus market view after margin removal.
4. **Football 1 fair probability** — our jury/model estimate.
5. **Football 1 fair odds** — `1 / fair_probability`.
6. **Price edge / discrepancy** — explicitly defined and documented.

The UI must never make the market benchmark look like an internally generated fair price.

---

## 8. Prophet / Trader / Movement / Portfolio product state

### Prophet

**Status: APPROVED PRODUCT ARCHITECTURE; research inputs partly implemented; final jury aggregation/product surface not complete.**

Existing research jurors provide a substantial base. The future Prophet should show a clear opinion rather than hiding behind risk language.

### Trader

**Status: CORE RESEARCH CONCEPT IMPLEMENTED IN MARKET comparison/backtests; product presentation still evolving.**

The Trader should remain price-obsessed and explicitly distinguish fair value from favourite selection.

### Movement

**Status: IMPLEMENTED PROSPECTIVE SHADOW RESEARCH; ZERO DECISION WEIGHT.**

Its main future economic question is not merely “did direction accuracy exceed 50%?” but:

> **Did using the frozen timing forecast improve the obtainable entry price, after accounting for cases where waiting lost the opportunity?**

### Portfolio

**Status: APPROVED PRODUCT LAYER / NOT YET TREATED AS A VALIDATED LIVE betting engine.**

Meaningful staking, concentration and portfolio rules must be separately specified and tested.

---

## 9. Interface doctrine

**Status: APPROVED — PRESERVE EXISTING DESIGN DIRECTION**

The current interface is generally right. Do not redesign it merely because more research modules now exist.

Immediate information should favour clarity:

- fixture;
- Prophet view;
- bookmaker price;
- Football 1 fair price;
- understandable discrepancy/edge;
- current action state when an action framework has actually been validated.

Technical material should be progressively disclosed:

- market de-vig methodology;
- jury breakdown;
- model disagreement;
- calibration;
- movement forecast;
- explanation details;
- research history.

**Clarity is king.**

Do not dump every model output onto the first screen.

---

## 10. On-device Apple-silicon direction

**Status: APPROVED TARGET; PARTIAL IMPLEMENTATION**

Native iPhone and macOS SwiftUI targets already exist, but full modelling remains Python-side.

The approved direction is to move core functionality on-device where practical:

- compact probability jurors;
- RF or equivalent tree representation where robust conversion is possible;
- at least one small neural juror if validated;
- local fair-price calculation;
- local explanation data;
- local cached research/fixture state where appropriate.

Cloud/API dependencies should be optional when possible, not fundamental to core inference.

Any Python → Core ML / Swift conversion must pass numerical regression tests before replacing the research source of truth.

---

## 11. Optional LLM juror

**Status: PROPOSAL ONLY**

An LLM may later serve as a qualitative-information juror or devil’s advocate rather than the primary match prophet.

Potential structured tasks:

- manager-statement extraction;
- injury/availability extraction;
- likely rotation;
- regime changes;
- fixture congestion/context;
- flags that a quantitative model may be missing relevant current information.

Preferred philosophy:

- on-device/small model first where practical;
- cloud/frontier escalation only when it demonstrates material additional value;
- no automatic decision weight.

Buzz is welcome only when the component earns its place empirically.

---

## 12. Automation, updates and rollback

**Status: PARTLY IMPLEMENTED / APPROVED FOR EXPANSION**

The repository already contains extensive GitHub Actions workflows for audits, ablations, model observers, movement research, odds archive, prospective snapshots, settlement and UI builds.

However, the current prospective protocol explicitly keeps live odds snapshots and settlement manual-only unless a new cadence is deliberately adopted.

Approved future automation includes:

- dependable data refresh;
- snapshot archiving;
- timestamp/schema validation;
- repeatable candidate scoring;
- scoring already-frozen forecasts;
- routine walk-forward research runs;
- research reports;
- health checks.

Meaningful model changes must still be discussed with David before activation.

Changes requiring explicit discussion include:

- giving a new juror decision weight;
- changing a label/target;
- changing feature-availability assumptions;
- changing market de-vig logic;
- changing pricing thresholds;
- changing staking/portfolio logic;
- changing calibration in a way that makes results non-comparable;
- replacing the source-of-truth model version.

Deployment planning should preserve:

- model versions;
- configs;
- schemas;
- research outputs;
- archived predictions/odds;
- rollback to the last known-good model/app;
- continued access to saved work after updates.

---

## 13. Separate Prophet and Trader scorecards

The product should maintain two visibly different evaluation concepts.

### Prophet scorecard

Measure:

- H/D/A log loss;
- Brier score;
- calibration;
- high-confidence calibration;
- draw calibration;
- ranking/discrimination;
- scoreline quality when available.

### Trader scorecard

Measure:

- discrepancy between available price and fair price;
- closing/common-book value;
- entry-price improvement from timing;
- opportunity loss caused by waiting;
- realised P&L for predeclared rules;
- drawdown;
- risk-adjusted performance;
- exposure/concentration.

A winning favourite does not prove that passing its price was a mistake.

---

## 14. Commercial/access constraints

**Status: APPROVED PRODUCT CONSTRAINTS**

- Free or inexpensive data/model access remains part of the experiment.
- Avoid unnecessary dependence on expensive per-call inference.
- Intrusive advertising is unwanted.
- Discreet sponsorship may be explored later if it does not damage trust or clarity.
- Sponsorship must never influence fair-price calculations, ranking, candidate generation, model weighting or explanations.
- Intended development credit: **Godo and Dave**.

---

## 15. Master implementation/proposal table

| Area | Status on 7 Sep 2026 | Notes |
|---|---|---|
| Historical EPL ingestion/audit/database | **IMPLEMENTED** | Python research pipeline |
| Market baseline / de-vigging | **IMPLEMENTED** | Bet365 historical benchmark; live consensus differs |
| Fixed-market residual slant | **IMPLEMENTED / RETAINED** | Negative overall result preserved |
| Mispricing backtest | **IMPLEMENTED** | Historical thresholds not validated strategies |
| Elo | **IMPLEMENTED RESEARCH** | Python + research artefact + iPhone Elo component |
| Bayesian strength | **IMPLEMENTED RESEARCH** | Includes ablation |
| Home/away | **IMPLEMENTED RESEARCH** | Includes ablation |
| Head-to-head | **IMPLEMENTED RESEARCH** | Includes ablation; predictive value not assumed |
| Promotion prior | **IMPLEMENTED RESEARCH** | Existing audit path |
| Poisson scoreline | **IMPLEMENTED RESEARCH** | Explicit score grid and draw probability |
| Dixon–Coles | **IMPLEMENTED RESEARCH** | Low-score dependence |
| Davidson | **IMPLEMENTED RESEARCH** | Explicit draw factor |
| Correlated score | **IMPLEMENTED RESEARCH** | Includes ablation |
| Non-transitive/matchup research | **IMPLEMENTED RESEARCH** | Existing module |
| Model disagreement/confidence observers | **IMPLEMENTED RESEARCH** | Existing modules/workflows |
| Random-forest residual | **IMPLEMENTED RESEARCH** | Walk-forward, fixed weight, zero live promotion from audit |
| RF user-facing explanations | **PARTIAL / PROPOSED** | Impurity importance exists; local faithful explanation needed |
| Closing/movement research | **IMPLEMENTED RESEARCH** | Multiple models/observers |
| Live odds ingestion | **IMPLEMENTED** | API-aware research utility |
| Odds archive | **IMPLEMENTED** | Prospective snapshots present |
| Prospective probability ledger | **IMPLEMENTED** | Immutable protocol/hash design |
| Prospective movement ledger | **IMPLEMENTED SHADOW** | Decision weight 0.0 |
| iPhone SwiftUI app | **IMPLEMENTED UI PROTOTYPE** | Not full on-device model inference |
| macOS SwiftUI app | **IMPLEMENTED UI PROTOTYPE** | Python remains source of truth |
| Draw-specific cross-model calibration audit | **APPROVED NEXT RESEARCH** | Build on existing draw models |
| Small neural juror | **APPROVED PROPOSAL** | Not implemented in current research tree |
| Full Core ML/on-device jury | **APPROVED TARGET** | Partial native UI only today |
| Prophet/Trader product separation | **APPROVED ARCHITECTURE** | Final UI/data contract incomplete |
| ACT/WAIT/WATCH movement thresholds | **RESEARCH PROPOSAL** | Not active; must be frozen/tested prospectively |
| Portfolio execution layer | **APPROVED PRODUCT LAYER** | Not a validated live strategy |
| LLM qualitative juror | **PROPOSAL** | Zero weight if/when researched |
| Routine automation | **PARTLY IMPLEMENTED / EXPAND** | Many Actions exist; live cadence remains deliberate |
| Rollback/versioned deployment discipline | **APPROVED ENGINEERING REQUIREMENT** | Formalize before autonomous model activation |
| Intrusive advertising | **REJECTED** | Do not pursue |
| Discreet sponsorship | **POSSIBLE LATER** | Must remain independent |
| “Godo and Dave” credit | **APPROVED** | Intended development credit |

---

## 16. Immediate priorities before substantial new model development

### A. Draw audit across the models that already exist

Do not add another draw model until Davidson, Dixon–Coles, scoreline, correlated-score and market draw probabilities have been compared on calibration, discrimination and scoreline structure.

### B. Existing-jury performance inventory

Create/maintain a concise results registry showing for each juror:

- exact target;
- features;
- timestamp policy;
- walk-forward specification;
- benchmark;
- log loss/Brier/calibration;
- negative findings;
- current product/decision weight.

### C. Fair-price UI/data-contract audit

Make sure every interface view distinguishes the de-vigged market benchmark from Football 1’s fair-price estimate.

### D. RF explanation design

Build a faithful explanation path before presenting the RF as an explainable product juror.

### E. Neural research specification

Only after the existing jury audit, define one modest neural experiment with a frozen architecture-selection and validation plan.

### F. Continue prospective movement accumulation at zero weight

Score new frozen forecasts without rewriting the 4 September predictions and without creating a timing rule from already-inspected observations.

### G. Automation/rollback plan

Automate repeatable operations while preserving explicit human approval for meaningful model activation.

---

## 17. Definition of a valid improvement

A change is not a valid improvement merely because it:

- raises in-sample accuracy;
- explains a famous match;
- looks impressive on previously inspected fixtures;
- creates a persuasive chart;
- or sounds football-intelligent.

A model earns promotion only if it improves a pre-defined objective under valid time-ordered evaluation and survives sanity checks.

For price/trading changes, the final question is:

> **Does this help us identify or obtain genuinely better prices, with acceptable risk, on data that was not used to invent the rule?**

---

## 18. Maintenance rule

This file is the top-level project state document.

When a meaningful research or product status changes:

1. update the relevant section/status;
2. record the date;
3. link the implementation/experiment where practical;
4. preserve superseded or negative results rather than rewriting history;
5. keep frozen protocol/result documents frozen unless a correction is explicitly documented.

**Conversation is for exploration. Version-controlled documentation is the project record.**
