# October prospective continuity checkpoint

Recorded 10 October 2026. This resumes the repository at `abda3cfa283019da8dcb3d83cea836c19236eb2b` after interrupted conversation delivery. Git commits and frozen files, rather than conversational claims, are the evidence.

## Saved evidence

- `prospective/ledger.jsonl`: 39 prediction records at the checkpoint.
- `prospective/settlements.jsonl`: 30 September settlements at the checkpoint.
- October manifest: `prospective/shadows/2026-10-10-12/manifest.json`.
- October snapshot retrieval: `2026-10-10T11:51:51.936218+00:00`.
- Nine October predictions and unchanged 15-day/30-day recency shadows; both shadows have zero decision weight.
- Training cutoff: 20 September 2026; 5,370 historical matches.
- Arsenal–Leeds was already underway before the October snapshot. It was deliberately excluded. The nine-match sample is a partial slate, not a complete matchweek, and must not later be enlarged with a reconstructed forecast.
- Draw Possibility was not generated for October because the original frozen historical reference was unavailable. Its original SHA-256 is retained in the manifest. September's saved Draw shadow predictions remain separate evidence; they cannot supply the missing October ranking.

## October evaluation

`src/football1/october_slate_report.py` and `.github/workflows/prospective-slate-2026-10-10-12.yml` add execution of the existing evaluation rules for this batch. This is an engineering continuation of the prospective protocol and September scorers, not a newly selected research rule or a claim that the implementation itself was frozen at the original snapshot time.

The evaluator pins the original manifest bytes by SHA-256, then verifies its exact prediction IDs/content hashes and both shadow-file hashes. It checks pre-kickoff timing, prevents duplicate or missing sample members, and selects settlements only for those nine original prediction IDs. A later snapshot cannot replace a frozen prediction.

The report supports zero, partial and all nine settlements. It includes:

1. Primary model versus market multiclass log loss and Brier score, using the existing fixed threshold sensitivity panel only as descriptive research.
2. Original, 30-day and 15-day probabilities versus market on exactly the same settled events.
3. Existing probability-error anatomy, including draw-specific errors.
4. Existing portfolio observer, with zero official bets and shadow accounting labelled separately.
5. Explicit `unavailable_at_freeze` Draw Possibility status, never a fabricated score or ranking.

Final scores must agree with the outcome label. Each settlement's stored scores are independently checked using `-log(p_actual)` and `sum((p_k - I[k=actual])**2)`. A hypothetical one-unit winning bet returns `decimal_odds - 1`; every losing choice returns `-1`. The selected outcome, recorded EV and selected P&L must match the original prediction. These checks validate internal arithmetic and identity; they do not independently authenticate an external final score.

Run without network or model fitting:

```bash
python -m football1.october_slate_report --output /tmp/october-slate-report.json
```

The workflow runs on relevant pull requests and master changes, including settlement-file changes, and can be manually dispatched. It does not fetch results or odds, alter forecasts, refit models, change a threshold, activate stakes, or adopt a scheduled API cadence. Commits made by GitHub Actions using its default token may not trigger another push workflow; in that case dispatch the evaluation manually. The source manifest and shadows remain committed; downloadable report artifacts expire after 90 days and can be reproduced from the source evidence.

## Next operational steps

- Settle the nine matches only after completed results are verified, retaining result provenance and appending to the separate settlement ledger.
- Run the October report after settlement updates. Keep partial reports labelled partial; a complete nine-match report is still a small sample, not proof of an edge.
- Recover the old Draw reference only if its bytes match the recorded original hash. Even successful later recovery must not be represented as an October pre-kickoff shadow lock. If a new reference is needed for future slates, version and freeze it before those future decisions.
- Keep small required reference objects in durable versioned storage with content hashes. Never rely on an expiring Actions artifact as the sole copy; large data/model files remain outside git under `AGENTS.md`.
- Use `PROJECT_NAMING.md` for the eventual rename. No name has been selected.
