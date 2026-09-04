# Football 1

EPL-first football probability and market-mispricing research project.

## Phase 1

Build a reproducible historical EPL database from Football-Data.co.uk, retaining raw source files and creating a canonical match table suitable for strict chronological research.

Initial pipeline:

`Football-Data.co.uk CSV -> immutable raw files -> canonical match rows -> validation -> later feature engineering -> walk-forward model -> calibrated probabilities -> bookmaker comparison`

## Non-negotiable research rules

- No random train/test split for forecasting.
- No data from the future may enter a feature.
- Same-match outcome/statistics must never be used to predict that match.
- Preserve raw data unchanged.
- Record source and retrieval timestamps.
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

This downloads season-start years 2012 through 2026 inclusive. For example, 2026 means season 2026/27.

By default files are stored under:

```text
data/raw/football-data/
```

The downloader uses the Football-Data.co.uk season-file pattern:

```text
https://www.football-data.co.uk/mmz4281/{SEASON_CODE}/E0.csv
```

Examples: `2526`, `2627`.

## Next milestones

1. Confirm historical file coverage and schema changes by season.
2. Build a canonical SQLite match database.
3. Classify every field by time-of-availability.
4. Add leakage-safe lagged team features.
5. Create walk-forward baseline models.
6. Remove bookmaker overround and compare model vs market probabilities.
7. Add current odds/API ingestion.
8. Add Swift/macOS UI only after the research pipeline is tested.
