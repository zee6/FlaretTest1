# Football 1

EPL-first football probability and market-mispricing research project.

## Phase 1

Build a reproducible historical EPL database from Football-Data.co.uk, retaining raw source files and creating a canonical match table suitable for strict chronological research.

Initial pipeline:

`Football-Data.co.uk CSV -> immutable raw files -> audit -> canonical match rows -> validation -> feature engineering -> walk-forward model -> calibrated probabilities -> bookmaker comparison`

## Non-negotiable research rules

- No random train/test split for forecasting.
- No data from the future may enter a feature.
- Same-match outcome/statistics must never be used to predict that match.
- Preserve raw data unchanged.
- Record source and retrieval timestamps.
- Keep pre-closing and closing odds distinct.
- Model quality will ultimately be judged by out-of-sample probability calibration and realistic betting P&L, not headline classification accuracy.

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

Audit the downloaded raw files before building anything predictive:

```bash
football1-audit-data \
  --input-dir data/raw/football-data \
  --output data/processed/raw_audit.json
```

Build the canonical SQLite database:

```bash
football1-build-db \
  --input-dir data/raw/football-data \
  --output data/processed/football1.sqlite
```

This treats season arguments as season-start years: 2026 means season 2026/27.

Raw files are stored under `data/raw/football-data/` and are deliberately excluded from Git. The downloader uses the Football-Data.co.uk season-file pattern:

```text
https://www.football-data.co.uk/mmz4281/{SEASON_CODE}/E0.csv
```

Examples: `2526`, `2627`.

## Odds timing

Football-Data documents two odds snapshots from 2019/20 onward: an earlier/pre-closing set and closing odds whose column headings contain `C`. Pinnacle closing 1X2 odds are also available farther back. Football 1 stores and audits these separately; a backtest may use only the snapshot that was genuinely available at its simulated decision time.

Pinnacle data from the source is explicitly flagged for seasons 2025/26 onward because Football-Data warns that its Pinnacle feed has been unreliable/stale since July 2025.

## Next milestones

1. Run the audit over the full historical EPL corpus and review schema/odds coverage.
2. Build and validate the canonical SQLite database.
3. Add leakage-safe lagged team features.
4. Establish bookmaker-only probability baselines after removing overround.
5. Create strict chronological/walk-forward baseline models.
6. Compare model probabilities against market probabilities OOS.
7. Add current odds/API ingestion.
8. Add Swift/macOS UI only after the research pipeline is tested.
