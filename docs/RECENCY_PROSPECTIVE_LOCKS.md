# Football 1 — Prospective Recency Shadow Locks

**Status date:** 9 September 2026  
**Decision weight:** 0 for every recency shadow  
**Primary prediction ledger:** unchanged

This document records the pre-kickoff evidence trail for recency candidates on the still-future 12–14 September EPL slate.

The recency candidates were selected after inspecting historical research. They are therefore **not untouched historical confirmation**. Their value from this point onward comes from being frozen before the future match results are known and then scored without changing the model or choosing fixtures after settlement.

## Common source

Both shadows use:

- the same 10 future event IDs from the original 4 September prospective Football 1 ledger,
- the same immutable source prediction record IDs and content hashes,
- the original 4 September market-consensus anchors,
- the frozen 4 September canonical historical database,
- historical training data only through 31 August 2026,
- alpha 0.10 fixed-market residual architecture,
- zero betting/staking decision weight.

Neither shadow uses the results from the completed 4–6 September matchweek.

## 30-day shadow — original pre-match lock

Model ID:

`fixed_market_offset_football_slant_v1_recency_30d_prospective_shadow`

Original lock time:

`2026-09-09T09:31:02Z`

GitHub Actions run:

`34335029540`

Artifact:

- name: `epl-prospective-recency-shadow`
- artifact ID: `10097381591`
- artifact ZIP digest: `sha256:fe4ba6e8ed229240e913e6c48c825a17c682665286c73461df774e17447128e6`
- uncompressed `recency_shadow.jsonl` SHA256: `28de0ae556d1e9f24ee7491118a7ab06ba439563a808b6f49eaa7a581120400c`
- records: 10

The 30-day setting came from inspected historical Recency Audit v1. It remains exploratory and zero-weight.

## 30-day refactor equivalence check

After parameterizing the shadow engine to support the 15-day sibling, the 30-day workflow was rerun before any 12 September kickoff.

Run:

`34337404705`

Artifact:

- artifact ID: `10098279287`
- ZIP digest: `sha256:444f619767b8ce6befe94db6605a391af34b93a49ef09ceda3c1603a598855c7`
- lock time: `2026-09-09T09:55:41Z`
- records: 10

The event IDs were identical to the original 30-day lock. Across all H/D/A probabilities, the maximum absolute numerical difference between the original 09:31 lock and the refactored 09:55 run was approximately `3.33e-16`, i.e. floating-point noise only. The refactor therefore did not materially change the 30-day model output.

The **09:31:02Z artifact remains the canonical first 30-day prospective lock**.

## 15-day shadow — pre-match lock

Model ID:

`fixed_market_offset_football_slant_v1_recency_15d_prospective_shadow`

Lock time:

`2026-09-09T09:55:46Z`

GitHub Actions run:

`34337404778`

Artifact:

- name: `epl-prospective-recency-shadow-15d`
- artifact ID: `10098282526`
- artifact ZIP digest: `sha256:7e311f6552a7b1df7718a593ddc802db62706b8a45ecf6cb676acda36b3b4990`
- uncompressed `recency_shadow_15d.jsonl` SHA256: `c3fcbe7ebd207f3fffd19f0b07b1bf2d3ed763d2343b7e7c59055f589729aef5`
- records: 10

The workflow asserts:

- all 10 fixtures kick off on or after 12 September 2026,
- there are 10 unique event IDs,
- decision weight is zero,
- half-life is exactly 15 days,
- the model ID is the separate 15-day shadow ID.

The 15-day setting was inspected **after** the earlier 30-day historical result and was marginally best among the observed historical recency probes. It is therefore explicitly post-hoc historically. Only future untouched results can add new evidence.

## Difference between 15 and 30 days

The 15-day and 30-day files contain the same 10 event IDs. Their probabilities are similar rather than radically different, as expected from changing only the decay speed.

The largest single-outcome probability difference between the two shadows on this slate is approximately **0.50 percentage points**. This makes the future comparison a sensitivity test of recent-form weighting rather than a comparison of unrelated models.

## Settlement plan

After every 12–14 September fixture is final, score the exact common 10-event sample on:

1. market consensus,
2. original equal-weight Football 1,
3. 30-day recency shadow,
4. 15-day recency shadow.

Primary metrics:

- multiclass log loss,
- multiclass Brier score.

Secondary descriptive diagnostics can include realized draw probabilities and H/D/A argmax accuracy, but no threshold, model weight, stake rule or half-life may be selected from this single 10-match batch.

## Governance

- Do not replace the original Football 1 prospective predictions.
- Do not replace the canonical 30-day lock with the later refactor-equivalence run.
- Do not call 15 days validated because it was historically marginally better.
- Do not tune another half-life from the 12–14 September outcomes.
- Preserve negative results.
