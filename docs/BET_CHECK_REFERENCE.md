# Bet Check — Synchronized Reference Bridge v1

Status: backend/data-contract implementation. Read-only. No Swift/UI activation.

## Why this exists

Bet Check must not compare quantities observed at different times without saying so.

A user may enter a price that is current now. Football 1 therefore needs a market benchmark, Football 1 model probability and best observed price built from the **same live snapshot** wherever possible.

The synchronized reference bridge prevents this failure mode:

`09:00 Football 1 probability` + `10:00 best bookmaker quote` → misleading comparison.

## Reuse of the prospective engine

`src/football1/bet_check_reference.py` reuses `build_prospective_records(...)` in read-only mode.

That means one live snapshot is used to:

1. create the market consensus probabilities,
2. anchor the frozen Football 1 residual model,
3. calculate the Football 1 probabilities,
4. retain the exact snapshot timestamp,
5. attach the best directly comparable sportsbook quote from that same snapshot.

No record is appended to `prospective/ledger.jsonl` by this bridge.

The prospective ledger remains the immutable research record; Bet Check references are transient current-analysis data.

## Timing rule

The join is strict:

- `prediction_record.snapshot_retrieved_at_utc`
- and the quote-board snapshot timestamp

must be identical.

If they differ, the reference builder raises an error rather than silently mixing them.

## Sportsbook best price versus exchanges

The current provider UK universe contains both sportsbooks and exchanges.

Known exchanges are excluded from the default `best_observed_price` field:

- Betfair Exchange,
- Matchbook,
- Smarkets.

Their raw back quotes can be useful market information, but the raw API price does not encode the user's exchange commission terms. Bet Check therefore does not present a raw exchange quote as though it were directly identical to a sportsbook decimal return.

## Market anchor remains unchanged

This bridge does **not** alter the existing prospective market-consensus policy.

That is intentional. The current Football 1 prospective model was designed and locked using the existing UK consensus universe. Changing which sources enter the consensus would change the model anchor and requires a separate governed audit.

The bridge therefore makes only this distinction:

- probability/model anchor: existing prospective policy, unchanged;
- executable `best_observed_price`: known exchanges excluded unless net commission can be handled honestly.

## Reference contract

Each synchronized event reference contains:

- event ID,
- snapshot timestamp,
- kickoff time,
- teams,
- de-vigged market H/D/A probabilities,
- Football 1 H/D/A probabilities,
- best observed sportsbook H/D/A quote with bookmaker provenance,
- number of eligible sportsbook quotes checked,
- source model identity,
- exact timing-match flag.

This object is directly consumable by `football1.bet_check.evaluate_bet(...)`.

## Apple-silicon path

The final iPhone/macOS implementation can mirror the same sequence:

`fresh odds data`
→ `local current Football 1 probability calculation`
→ `local synchronized reference object`
→ `local Bet Check arithmetic`
→ `local explanation templates`.

The network supplies fresh external facts. It does not need to perform the reasoning.

## Governance

- No ledger write.
- No LLM.
- No cloud reasoning.
- No betting execution.
- No later-price / earlier-model timestamp mixing.
- No exchange quote promoted as sportsbook best without net commission handling.
- No change to the prospective market anchor in this feature.
