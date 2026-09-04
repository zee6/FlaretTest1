# Football 1 Prospective Validation Protocol

This protocol exists to preserve genuinely unseen evidence after the historical research phase.

## 1. Predictions are immutable

Each prospective prediction is written before kickoff to `prospective/ledger.jsonl`.

A prediction record contains its provider event id, snapshot timestamp, kickoff timestamp, market consensus, best recorded H/D/A prices, Football 1 probabilities, feature vector, model identity and a SHA-256 content hash.

Existing prediction records must never be edited after kickoff. New snapshots of the same fixture are allowed only as new records with new timestamps and record ids.

## 2. Settlement is separate

Results are appended later to `prospective/settlements.jsonl`. A settlement references both the original prediction record id and its exact content SHA-256.

Settlement must not modify the prediction file.

Only provider events explicitly marked completed may settle.

## 3. Primary prospective probability test

The primary model question is whether Football 1 improves probability quality relative to the recorded live market anchor.

Report, on the same settled records:

- mean multiclass log loss for Football 1;
- mean multiclass log loss for the market;
- Football 1 minus market log-loss delta;
- mean multiclass Brier score for Football 1;
- mean multiclass Brier score for the market;
- Football 1 minus market Brier delta.

Lower log loss and lower Brier score are better. Negative model-minus-market deltas favor Football 1.

Do not judge this test from a handful of matches.

## 4. Live anchor change is explicit

Historical residual-model research used de-vigged Bet365 pre-closing probabilities as its market anchor.

The prospective feed currently uses the mean of individually de-vigged complete UK 1X2 bookmaker triplets supplied by The Odds API. Bet365 is not assumed to be present.

Therefore the prospective implementation is explicitly labelled experimental and not historically equivalent to the Bet365-anchored backtest.

## 5. Historical EV thresholds are not validated strategies

The historical fixed-threshold sensitivity grid was:

- 2.5%
- 5.0%
- 7.5%
- 10.0%

Those thresholds remain a fixed reporting panel prospectively so results can be compared with the historical observations. They are not a mechanism for choosing a strategy after outcomes are known.

No threshold should be promoted because it happens to have the best realized prospective ROI after inspection.

Every settlement records unit P&L for all three H/D/A choices at the prices captured in the prediction record. This preserves later analysis without rewriting the prediction.

## 6. No retrospective repairs

If a data-source mapping, feature, model or anchor needs to change, make a new model/version and record the change prospectively. Do not rewrite earlier predictions so they conform to the new version.

If an operational/data error invalidates a prediction, preserve the original record and document the invalidation separately rather than deleting it.

## 7. Multiple snapshots

Multiple pre-kickoff snapshots of one event may eventually be useful for price-movement analysis. Each is a separate prediction record and is scored separately unless an analysis explicitly collapses events to a pre-declared decision timestamp.

Never select whichever snapshot had the best hindsight performance.

## 8. API quota discipline

Live odds snapshots are manual-only unless a future cadence is explicitly adopted. Current UK `h2h` odds calls have consumed one provider usage credit per snapshot in live tests.

Settlement is also manual-only. Scores calls with completed-game history should be made only when there are unresolved predictions worth settling.

## 9. Current prospective model

The first prospective model is:

`fixed_market_offset_football_slant_v1_live_consensus_anchor`

with residual regularization `alpha = 0.10` fixed before the prospective run.

The first locked snapshot was recorded on 2026-09-04 before all 20 included fixtures kicked off. No betting threshold was selected for that snapshot.
