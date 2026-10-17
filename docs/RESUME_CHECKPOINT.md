# Football 1 — resume checkpoint

Last verified: 17 October 2026, before the weekend's first kickoff. Development: Godo and Dave. Repository: `zee6/FlaretTest1`, branch `master`.

## Start here

Read `AGENTS.md`, `docs/PROJECT_STATE.md`, then this checkpoint. The repository is the authoritative durable copy. If an old workspace was cleaned up, clone the repository again; do not treat missing scratch files as missing project evidence.

This session's goal was to check readiness for the 17–19 October EPL matches. No forecasts for this slate were present initially. The manual snapshot workflow was launched through a temporary, path-scoped master push trigger. The operational run succeeded, saved its records, and the follow-up change restores the original manual-only workflow. No weekly schedule was enabled.

- Launch PR: [#80](https://github.com/zee6/FlaretTest1/pull/80).
- Successful snapshot run: [39022856403](https://github.com/zee6/FlaretTest1/actions/runs/39022856403).
- Frozen-evidence commit: `51176f0d50c637973b2372f6524144e51dd33788`.
- Original manual workflow content is from `899e76795a67e478ecec48d89dc8801d28168268:.github/workflows/prospective-snapshot.yml`.

## What is ready

All ten 17–19 October fixtures have original pre-kickoff primary forecasts and the existing 15- and 30-day recency observers. The market snapshot was retrieved at **2026-10-17T09:54:42.103887+00:00**, or **11:54:42 Swiss time**. The manifest was written at **2026-10-17T09:54:54.787055+00:00**, before Everton–Chelsea's **11:30 UTC / 13:30 Swiss** kickoff.

The fresh historical database contains **5,380 training matches**, with data cutoff **12 October 2026**. This is the existing alpha=0.10 model specification. Future forecasts may use earlier completed matches; no new match result was used to forecast itself. Recency and movement observers retain zero decision weight. Official betting remains inactive: zero bets, stake and official P&L.

| Date | Fixture | Kickoff, Europe/Zurich |
|---|---|---|
| 17 Oct | Everton – Chelsea | 13:30 |
| 17 Oct | Manchester City – Ipswich Town | 16:00 |
| 17 Oct | Brentford – Liverpool | 16:00 |
| 17 Oct | Fulham – Hull City | 16:00 |
| 17 Oct | Newcastle United – Aston Villa | 18:30 |
| 18 Oct | Bournemouth – Sunderland | 15:00 |
| 18 Oct | Leeds United – Manchester United | 15:00 |
| 18 Oct | Brighton and Hove Albion – Crystal Palace | 15:00 |
| 18 Oct | Nottingham Forest – Arsenal | 17:30 |
| 19 Oct | Tottenham Hotspur – Coventry City | 21:00 |

The provider returned **20 future fixtures**. The existing snapshot workflow therefore locked **10 additional primary and movement forecasts for 23–25 October**, as well as this week's ten. These are also immutable originals. The dated recency manifest covers only **17–19 October's ten**, not all 20. The iPhone Results batch is grouped by snapshot and consequently displays the date range **17–25 October** with 20 pending matches at this checkpoint. Do not mistake that for 20 matches this weekend.

## Frozen files and integrity

Current-week manifest: `prospective/shadows/2026-10-17-19/manifest.json`.

Manifest SHA256: `7772fe8e28d2549be76054effcbdb5ef593129aefcfabf8122324256ab78f609`.

| File | Records | SHA256 at checkpoint |
|---|---:|---|
| `prospective/ledger.jsonl` | 59 | `4224cfe561591ecec95b49644ba30a3ddeee6b66b783605002fdc454f10dc481` |
| `prospective/settlements.jsonl` | 35 | `b88c8d8ad3a7cb3f2043706b5136b9718aab4fb125615ef69a26220d47a6c22f` |
| `prospective/movement_predictions.jsonl` | 58 | `c650254b4408497ed6e3aeb10c3bc9c26898f4140c7e70ee582a187f4f16ed3e` |
| `prospective/odds_snapshots.jsonl` | 77 | `e9b8f3abff84b90e253af60bda23d082856cc68e23592f705b216960056d29d6` |
| `prospective/mobile_results.json` | 4 snapshot batches | `fa39a220cb52de5feb13943baeef44c50486f0b2eaa30685b2e1d2f218840ede` |
| `prospective/shadows/2026-10-17-19/recency_15d.jsonl` | 10 | `684e90200bcd4daa8e4a11346e3a4b7a45d629069697274d06edc0f378eec642` |
| `prospective/shadows/2026-10-17-19/recency_30d.jsonl` | 10 | `c23a2bf5ce61fe091eb9ee314cb2e5dea7fa98974937df51c3ee5e128f66ff65` |

The manifest records exact source prediction IDs/hashes, original snapshot time, recency file hashes/lock times, database SHA256 `1aa8b7f883b46cad55de23e9ebe2332d992757a64fdc3de6fa1b0680793044dd`, raw snapshot SHA256 `a289bb97229aefd829a63cde248c17aa852c5bb7aa3054fd5a4226c976287172`, and run ID. The raw live input is in the run's `prospective-live-input` artifact with the existing seven-day retention; do not assume it survives indefinitely. The original normalized odds, forecast probabilities and recency JSONL files are committed in git.

Independent checks verified every content hash, prediction-to-shadow link, timing, probability sum and zero observer weight; all earlier 39 primary predictions, 38 movement records and 57 archived odds records remain byte-for-byte prefixes of the new ledgers. The 35-settlement file is unchanged. Exact current-week fixture coverage was compared with the published schedule. The mobile feed's probabilities match the frozen ledger, and its unsettled scores/ROI are unavailable rather than invented zeros.

## Known gaps — preserve these distinctions

- Draw Possibility remains unavailable for this new slate because its original fixed September historical reference database is unavailable. The existing Draw generator labels that reference as the frozen 4 September database. Do not silently feed it a different database, change the reference, or fabricate an original lock.
- The separate legacy `prospective-consensus-movement` integrity replay still fails while downloading expired database artifact/run `33924106948`. Its focused tests pass. This is separate from the successful live snapshot workflow, which builds its own current database. Do not hide the failed replay or describe all CI as green.
- The 10–12 October slate remains at **5/9 recorded settlements**. Four older final results still need verified append-only settlement: Hull–Everton, Crystal Palace–Nottingham Forest, Liverpool–Manchester City and Coventry–Newcastle. They are unrecorded results, not future matches.
- Totals are **59 predictions / 35 settlements / 24 unresolved records**: those four older results plus 20 future fixtures. Never count unresolved records as losses, wins, zero log loss or zero ROI.
- The existing primary model has not established an overall edge over the market. Preserve the negative interim October findings. No threshold, strategy, stake rule, model weight or naming change was activated.
- The app is a native SwiftUI interface reading Python-generated public data; full model inference has not been migrated to Swift/Core ML. Naming remains undecided; use the existing naming notes.

## Resume in this order

1. Pull or clone current `master`; read this checkpoint and inspect subsequent commits before changing evidence. Verify the dated manifest hash and source identities. Ledger-wide hashes may change only through legitimate new append-only records; the dated frozen manifest and shadow files must not be edited.
2. Append independently verified final scores for the four outstanding 10–12 October fixtures. Re-run the pinned October evaluator on its exact original nine-match sample, not the latest 20-fixture snapshot.
3. Settle the 17–19 October sample as final scores become available. Select its exact ten source IDs from the dated manifest and score primary, market and both fixed recency observers on the same settled subset. Do not pool in the ten 23–25 October fixtures. A dedicated report for this new manifest has not yet been added; the existing October evaluator is intentionally pinned to the earlier slate.
4. Regenerate `prospective/mobile_results.json` in the same change as any ledger append; verify with `python -m football1.mobile_results --check`. Run `python -m pytest -q` after meaningful code changes.
5. Remember that the 23–25 October primary/movement forecasts are already locked. Any further shadow work must be prospective, explicitly timestamped and linked to their original source forecasts; never overwrite the original probabilities or substitute later prices.
6. Review recurring forecast/settlement scheduling so weekly readiness does not depend on a manual health check. The forecast workflow is manual-only at this checkpoint. Model activation remains a separate discussion with David.

Validation this session: the existing Python suite passed in the operational workflow; all operational steps completed successfully. The follow-up PR also runs the suite against the now-expanded committed ledgers. The iPhone Results interface was merged in PR #79 after Swift contract tests, a native simulator build and screenshot inspection.
