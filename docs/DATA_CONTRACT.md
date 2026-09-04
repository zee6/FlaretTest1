# Football 1 Data Contract

## Core principle

Every field must carry an explicit time-of-availability interpretation before it is allowed into a predictive feature set.

## Fixture identity / scheduling

Examples: `Date`, `Time` when supplied, `HomeTeam`, `AwayTeam`.

These identify the match. A date in a historical file is not, by itself, proof that every other column in that row was known before kickoff.

For historical seasons without sufficiently reliable kickoff ordering, all fixtures on the same calendar date are feature-snapshotted before any result from that date is applied to team state.

## Outcomes — NEVER same-match predictors

Examples: `FTHG`, `FTAG`, `FTR`, `HTHG`, `HTAG`, `HTR`.

These are targets/outcomes for the match.

## Post-match match statistics — NEVER same-match predictors

Examples include shots, shots on target, fouls, corners, cards, and source-supplied `HxG` / `AxG` when present.

They may be used only after lagging/rolling them so that a future match uses statistics from earlier completed matches.

## Bookmaker odds

Odds are pre-match market information, but exact timing semantics vary by field and season.

Rules:

- keep the original source column name;
- do not relabel an odds field as opening/pre-closing/closing unless documented;
- keep pre-closing and closing snapshots distinct;
- store quoted decimal odds unchanged;
- create separate implied-probability and de-vigged-probability values;
- the simulated decision timestamp must not precede known availability of the selected odds;
- recent Pinnacle fields remain warning-flagged where the upstream source warns of stale data.

## Raw layer

Raw CSV bytes are immutable and accompanied by source URL, UTC retrieval timestamp, SHA-256 and byte count.

Raw data is not committed to Git.

## Canonical layer

The canonical SQLite layer contains one stable match row plus the preserved source row payload and schema inventory. Canonical row counts must reconcile exactly to completed audited source rows.

## Historical model evaluation

All predictive evaluation is chronological. No random train/test split is permitted.

Phase 1C historical OOS outputs have already been observed and are frozen in `docs/PHASE1C_RESULTS.md`. New rules inspired by those outputs cannot be called untouched historical confirmation.

## Prospective prediction ledger

Future genuine confirmation evidence must be written before match results are known. Each ledger record should contain at minimum:

- immutable prediction/fixture ID;
- fixture date and kickoff time where known;
- UTC prediction/retrieval timestamp;
- data-source timestamps/availability status;
- bookmaker and raw quoted H/D/A odds;
- raw implied probabilities and de-vigged market probabilities;
- model probabilities;
- predicted EV by outcome;
- selected signal, if any, under the predeclared rule;
- model/version/commit hash;
- feature schema/version;
- result and realized P&L fields left null until outcome ingestion.

Result settlement must be a separate operation from prediction creation. Prediction fields are immutable after kickoff/result availability.
