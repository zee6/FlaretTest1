# Phase-1 Data Contract

## Core principle

Every field must carry an explicit time-of-availability interpretation before it is allowed into a predictive feature set.

## Initial classification

### Fixture identity / scheduling

Examples: `Date`, `Time` when supplied, `HomeTeam`, `AwayTeam`.

These identify the match. A date in a historical file is not, by itself, proof that every other column in that row was known before kickoff.

### Outcomes — NEVER same-match predictors

Examples: `FTHG`, `FTAG`, `FTR`, `HTHG`, `HTAG`, `HTR`.

These are targets/outcomes for the match.

### Post-match match statistics — NEVER same-match predictors

Examples commonly present in Football-Data files: shots, shots on target, fouls, corners, cards.

They may be used only after lagging/rolling them so that a future match uses statistics from earlier completed matches.

### Bookmaker odds

Odds are pre-match market information, but exact timing semantics vary by field and season.

Rules:

- keep the original source column name;
- do not relabel an odds field as opening or closing unless documented;
- store quoted decimal odds unchanged;
- later create separate derived implied-probability and de-vigged-probability fields;
- the simulated decision timestamp must not precede the known availability of the selected odds.

## Raw layer

Raw CSV bytes are immutable and accompanied by source URL, UTC retrieval timestamp, SHA-256 and byte count.

## Canonical layer

The next phase will create one canonical row per match with a stable match key, parsed dates, outcomes and explicitly grouped odds/stat fields.

No modelling starts until canonical validation checks pass.
