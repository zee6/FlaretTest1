# Football 1

EPL-first football probability and market-mispricing research project.

## Phase 1

Build a reproducible historical EPL database from Football-Data.co.uk, retaining raw source files and creating a canonical match table suitable for strict chronological research.

Initial pipeline:

`Football-Data.co.uk CSV -> immutable raw files -> audit -> canonical match rows -> validation -> leakage-safe features -> walk-forward probability models -> market comparison -> fixed-threshold tail tests`

## Non-negotiable research rules

- No random train/test split for forecasting.
- No data from the future may enter a feature.
- Same-match outcome/statistics must never be used to predict that match.
- Preserve raw data unchanged.
- Record source and retrieval timestamps.
- Keep pre-closing and closing odds distinct.
- Model quality is judged by out-of-sample probability calibration and realistic betting P&L, not headline classification accuracy.
- Negative OOS results are retained; do not tune them away.
- Historical sensitivity thresholds are reported as a grid, not cherry-picked as a validated strategy.

## Quick start

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Download EPL seasons:

```bash
football1-download-epl --from-season 2012 --to-season 2026
```

Audit and build the canonical database:

```bash
football1-audit-data --input-dir data/raw/football-data --output data/processed/raw_audit.json
football1-build-db --input-dir data/raw/football-data --output data/processed/football1.sqlite
```

Run the benchmark/model stack:

```bash
football1-market-baseline --database data/processed/football1.sqlite --output data/processed/market_baseline.json
football1-model-baseline --database data/processed/football1.sqlite --output data/processed/model_baseline.json
football1-slant-model --database data/processed/football1.sqlite --output data/processed/slant_model.json
football1-offset-slant --database data/processed/football1.sqlite --output data/processed/offset_slant.json
football1-mispricing-backtest --database data/processed/football1.sqlite --output data/processed/mispricing_backtest.json
```

Raw files are deliberately excluded from Git. The downloader uses the Football-Data.co.uk season-file pattern:

```text
https://www.football-data.co.uk/mmz4281/{SEASON_CODE}/E0.csv
```

## Odds timing

Football-Data documents two odds snapshots from 2019/20 onward: an earlier/pre-closing set and closing odds whose column headings contain `C`. Football 1 stores and audits these separately; a backtest may use only the snapshot genuinely available at its simulated decision time.

Pinnacle data from the source is explicitly flagged for seasons 2025/26 onward because Football-Data warns that its Pinnacle feed may be stale/unreliable in that period.

## Current empirical status

Phase 1C has been executed reproducibly in GitHub Actions against 15 real EPL season files (2012/13–2026/27). The current run contains 5,340 completed matches and the canonical database reconciles exactly to that count.

The broad football-only model, unconstrained market slant, and fixed-market residual model do not beat de-vigged Bet365 probabilities overall. The fixed-market residual architecture is nevertheless retained because zero residual adjustment reproduces the market exactly and it sharply reduces damage versus the unconstrained slant.

A fixed sensitivity grid on the residual model's strongest market disagreements produced positive historical ROI at the 7.5% and 10% EV thresholds, but these are explicitly **not validated strategies**: the threshold grid has already been observed, the model overstates expected returns, and results vary sharply by season.

See `docs/PHASE1C_RESULTS.md` for the frozen results and interpretation.

## Next milestones

1. Preserve Phase 1C as the historical benchmark; do not retune against its OOS outputs.
2. Add genuinely pre-match/current football information with explicit timestamps.
3. Create a prospective prediction ledger for future 2026/27 fixtures before results are known.
4. Compare prospective results against raw/de-vigged market probabilities and the frozen residual architecture.
5. Add current odds/API ingestion and caching.
6. Add richer pre-match team-strength/xG-derived features only where historical or live availability is timestamp-safe.
7. Build the Swift/macOS UI after the live research pipeline and signal contract are stable.
