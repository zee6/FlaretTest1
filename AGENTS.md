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

## Absolute modelling constraints

### No leakage

A feature for match `M` may use only information that was available before the decision timestamp for `M`.

Do not directly use same-match values such as final score, half-time score, result, shots, shots on target, corners, cards or other post-match statistics to predict that same match.

These fields may be ingested as outcomes or as inputs to future-match lagged/rolling features.

### Time splits only

Never use random train/test splits for predictive evaluation. Use chronological train/validation/OOS periods and, later, walk-forward validation.

### Market data

Keep raw bookmaker odds separately from derived probabilities. When comparing model probabilities with bookmaker probabilities: convert decimal odds to implied probabilities; explicitly remove overround; retain both raw and de-vigged values; never treat a closing price as available earlier than its actual timestamp. Do not infer an odds timestamp that the source does not provide.

### Evaluation

Record at minimum log loss, Brier score, calibration, multiclass accuracy as a secondary descriptive metric, expected value under quoted odds, and realised OOS P&L when a betting rule is tested.

Any betting backtest must use only odds known at the simulated decision time.

## Coding conventions

- Python 3.11+ for research/data work.
- Type hints on public functions.
- `pytest` for tests.
- Network calls must be mockable; unit tests must not require internet.
- Raise clear errors for corrupt files or impossible dates.
- Use UTC for retrieval timestamps.
- Keep football match date/time and odds timing semantics explicit.

## First task

Implement and verify the Football-Data.co.uk EPL downloader.

Acceptance criteria:

- maps 2026 -> `2627`, 1999 -> `9900`;
- constructs the EPL `E0.csv` URL;
- writes downloads atomically;
- does not overwrite an existing raw file unless `--force` is supplied;
- stores a SHA-256 sidecar for each downloaded file;
- writes a JSON metadata sidecar with source URL, retrieval UTC timestamp, byte count and SHA-256;
- validates that the returned content looks like CSV and includes `HomeTeam` and `AwayTeam`;
- unit tests do not make live network calls.
