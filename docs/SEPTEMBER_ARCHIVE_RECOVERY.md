# September evidence recovery — 11 October 2026

The original 4 September database artifact was retained for 14 days. Its source run now returns no artifacts. The canonical first 30-day recency shadow was also retained for 14 days and its run returns no artifacts. Neither object has been recovered. The repository has no release containing a backup; the dependent historical workflows uploaded reports rather than another database copy.

Two small original forecast files survived in 90-day artifacts. Both the downloaded ZIP hashes and the uncompressed JSONL hashes match the values recorded in September, before their matches were played:

| Original object | Artifact ID | Original JSONL SHA-256 |
|---|---|---|
| 15-day recency, 10 fixtures | `10098282526` | `c3fcbe7ebd207f3fffd19f0b07b1bf2d3ed763d2343b7e7c59055f589729aef5` |
| Draw Possibility, 10 fixtures | `10101426769` | `915b174364b631db6fcdfb6e675855dcf527ec18e214daea701ee7d7d6db17ed` |

The exact original JSONL bytes are now committed under `prospective/shadows/2026-09-12-14/`, with a separately dated `recovery_manifest.json`. This manifest documents recovery on 11 October; it is not represented as an original pre-match manifest. Record timestamps, probabilities, rankings, model IDs and hashes remain unchanged.

`september_recovery_report.py` pins that recovery manifest and all recovered file hashes. It selects exactly the original first 20 September prediction IDs and content hashes, preventing later forecasts from changing the historical report's sample. It reuses the existing primary, 15-day recency, Draw, probability-error, two-batch comparison and portfolio scorers. The original 30-day lane is explicitly unavailable: `full_30d_vs_15d_comparison_available` is false. No later lock, refitted model, interpolation or September 18–20 forecast substitutes for it.

The weekend evaluation workflow now runs this offline report from committed evidence. The former workflow depended on expiring downloads and asserted that the entire growing prediction ledger contained only 20 records. Fixing the sample to its original identities allows the first two batches to remain reproducible as newer slates accumulate. Other legacy pre-match-only workflows remain historical utilities; this recovered-evidence workflow is the maintained September rerun path.

```bash
python -m football1.september_recovery_report --output /tmp/september-recovery-report.json
```

Recalculation retains the negative findings. Across the first 20 matches, model log loss is 1.122591 versus market 1.113616; Brier is 0.692334 versus 0.685876. On the second ten-match batch, 15-day recency log loss is 1.183953 versus market 1.183617, and Brier is 0.739611 versus 0.738399. Lower is better in each case. These are already observed historical prospective results, not new confirmation evidence or grounds for activating a strategy.

Recovering September Draw forecasts does not recover the historical reference database and does not fill October's missing Draw shadow. October's frozen manifest and its omission remain unchanged.
