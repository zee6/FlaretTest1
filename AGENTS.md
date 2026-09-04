# Codex Instructions — Football 1

## Purpose

Build a rigorous EPL-first football probability and bookmaker-mispricing research system, later exposed through a native Apple-silicon application.

## Working style

- Make small, testable changes.
- Run tests after every meaningful change.
- Never silently weaken a test to make code pass.
- Prefer deterministic code and explicit data contracts.
- Preserve raw downloaded data exactly as received.
- Never commit API keys, tokens, credentials, virtual environments, model binaries, or large raw datasets.
- Add logging for downloads, row counts, parsing failures, duplicate matches, schema changes and missing fields.
- Preserve negative empirical results. Never retune a historical OOS specification merely because its score is disappointing.

## Absolute modelling constraints

### No leakage

A feature for match `M` may use only information that was available before the decision timestamp for `M`.

Do not directly use same-match values such as final score, half-time score, result, shots, shots on target, corners, cards, xG or other post-match statistics to predict that same match.

These fields may be ingested as outcomes or as inputs to future-match lagged/rolling features.

For historical files without reliable kickoff timestamps, Football 1 takes the conservative approach: all fixtures on one calendar date are snapshotted before any result from that date updates team state.

### Time splits only

Never use random train/test splits for predictive evaluation. Use chronological train/validation/OOS periods and walk-forward validation.

### Historical OOS is now observed

Phase 1C OOS results through the available 2026/27 sample have been inspected and are documented in `docs/PHASE1C_RESULTS.md`.

Therefore:

- do not describe any new rule chosen after Phase 1C as untouched historical confirmation;
- do not select the 7.5% or 10% historical tail threshold as a validated winner;
- if exploring additional historical specifications, label them exploratory and use training-only/nested selection where appropriate;
- prioritize prospective logging of future 2026/27 predictions for genuine new confirmation evidence.

### Market data

Keep raw bookmaker odds separately from derived probabilities. When comparing model probabilities with bookmaker probabilities: convert decimal odds to implied probabilities; explicitly remove overround; retain both raw and de-vigged values; never treat a closing price as available earlier than its actual timestamp. Do not infer an odds timestamp that the source does not provide.

Use Bet365 pre-closing as the principal full-history market benchmark unless a different source/timing choice is explicitly justified. Keep Pinnacle recent-feed warnings in force.

### Evaluation

Record at minimum log loss, Brier score, calibration, multiclass accuracy as a secondary descriptive metric, expected value under quoted odds, and realised OOS P&L when a betting rule is tested.

Any betting backtest must use only odds known at the simulated decision time.

Flat-stake diagnostic P&L uses:

- predicted EV = `model_probability * decimal_odds - 1`
- winning 1-unit bet P&L = `decimal_odds - 1`
- losing 1-unit bet P&L = `-1`

Always sanity-check stake, P&L, ROI and running drawdown calculations.

### Current retained architecture

The preferred probability architecture is a fixed-market residual slant:

- start from de-vigged bookmaker probabilities;
- treat market log-probabilities as the anchor/offset;
- learn only small football-information residual adjustments;
- zero residual adjustment must reproduce the market exactly.

The current alpha=0.10 residual model does not beat the market overall. Keep that negative result. Its historical tail sensitivity is exploratory only.

## Coding conventions

- Python 3.11+ for research/data work.
- Type hints on public functions.
- `pytest` for tests.
- Network calls must be mockable; unit tests must not require internet.
- Raise clear errors for corrupt files or impossible dates.
- Use UTC for retrieval timestamps.
- Keep football match date/time and odds timing semantics explicit.

## Next development target

Build the prospective 2026/27 prediction/odds ledger and richer timestamp-safe current-data ingestion. A prospective ledger row must be written before the associated match result is known and must include retrieval timestamp, fixture identity, quoted odds, de-vigged market probabilities, model probabilities, predicted EV, model/version hash and feature-availability metadata.
