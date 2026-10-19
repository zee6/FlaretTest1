# Football 1 — resume checkpoint

Last verified: **19 October 2026**, results checked at **18:53:17.884810 UTC**. Development: Godo and Dave. Repository: `zee6/FlaretTest1`, branch `master`.

## Start here

Read `AGENTS.md`, `docs/PROJECT_STATE.md`, then this checkpoint. The repository is the authoritative durable copy. If a workspace was cleaned up, clone the repository again; missing scratch files do not mean project evidence is missing. Inspect commits after this checkpoint before changing evidence.

The latest work appended **13 independently verified final scores**, evaluated both original October slates separately and regenerated the iPhone Results feed. See [the dated settlement report](OCTOBER_2026_SETTLEMENT_UPDATE_2026-10-19.md) for match-level accounting, source provenance and all model comparisons. Original forecasts, prices, manifests and observer files were not modified. No model, threshold, stake policy, name or decision weight was changed.

## Current results and pending work

- **59 original predictions / 48 settlements / 11 unresolved** across four snapshot batches.
- **10–12 October: complete, 9/9.** Primary mean log loss **1.108346**, market **1.087786**; primary Brier **0.677205**, market **0.661501**. Both recency shadows also trail the market. The one-unit every-match max-EV diagnostic is **−5.60 units on 9 staked**, **−62.22% ROI**, **8.00 units maximum drawdown** (1 win / 8 losses).
- **17–19 October: partial, 9/10.** Primary mean log loss **0.778606**, market **0.784034**; primary Brier **0.438626**, market **0.442921**. Both recency shadows improve slightly on the market but less than primary. The one-unit diagnostic is **+0.92 units on 9 staked**, **+10.22% ROI**, **1.80 units maximum drawdown** (4 wins / 5 losses).
- **Tottenham–Coventry on 19 October remains unresolved** at this verification. Its scheduled kickoff is **19:00 UTC / 21:00 Europe/Zurich**. Append a final score only after independently verifying completion. Do not infer a result from kickoff time.
- **Ten 23–25 October primary/movement forecasts are already locked.** They are the other ten unresolved records; they must not enter the current ten-match comparison. No recency/Draw originals are claimed for this later slate.
- Official policy remains `no_validated_betting_rule`: **zero bets, zero stake, zero P&L**. Official ROI is unavailable with zero turnover. Hypothetical gross quoted-price returns are separate, include negative-EV selections and have zero decision weight.

Small batch changes do not establish an overall model edge. The earlier negative interim report remains preserved at [OCTOBER_2026_PARTIAL_RESULTS.md](OCTOBER_2026_PARTIAL_RESULTS.md). Unresolved matches contribute no outcome, probability score, diagnostic stake or ROI.

The Results feed's newest batch is still **17–25 October**, with **9 settled / 11 pending**, because app batches group forecasts by snapshot time. The dated recency manifest covers only this weekend's ten fixtures. This date range does not imply twenty matches this weekend.

## Frozen evidence and integrity

| File | Records | SHA256 at this checkpoint |
|---|---:|---|
| `prospective/ledger.jsonl` | 59 | `4224cfe561591ecec95b49644ba30a3ddeee6b66b783605002fdc454f10dc481` |
| `prospective/settlements.jsonl` | 48 | `7da7aeb343e6506b8276ceab335a0e58a79e074a444912fc8e0a72954cfdb35e` |
| `prospective/movement_predictions.jsonl` | 58 | `c650254b4408497ed6e3aeb10c3bc9c26898f4140c7e70ee582a187f4f16ed3e` |
| `prospective/odds_snapshots.jsonl` | 77 | `e9b8f3abff84b90e253af60bda23d082856cc68e23592f705b216960056d29d6` |
| `prospective/mobile_results.json` | 4 snapshot batches | `43567af86ee928a255721d37b56e72b490b2ad241780d857a4590d2c18061269` |
| `prospective/shadows/2026-10-17-19/recency_15d.jsonl` | 10 | `684e90200bcd4daa8e4a11346e3a4b7a45d629069697274d06edc0f378eec642` |
| `prospective/shadows/2026-10-17-19/recency_30d.jsonl` | 10 | `c23a2bf5ce61fe091eb9ee314cb2e5dea7fa98974937df51c3ee5e128f66ff65` |

The 35 settlements present at the previous checkpoint are an identical byte prefix; only thirteen new lines were appended. [The verification record](../prospective/verified_results/2026-10-19.json) and the appended settlements identify source URLs, published final scores, original prediction IDs/hashes and the verification timestamp. Results were cross-checked against Football Web Pages, NBC and the structured EPL feed. These are manual published-source transcriptions, not a fetched provider scores response.

The registered evaluator pins each original manifest, prediction ID/hash and recency file. It validates pre-kickoff timestamps, settlement semantics and identical settled samples before calling the existing scorers:

| Registered CLI slate | Frozen sample | Manifest SHA256 |
|---|---:|---|
| `2026-10-10-12` (default) | 9 | `071490a0eeec925f0e3d1d276f9d2269141ec8ed73fc88d31c534732323b7850` |
| `2026-10-17-19` | 10 | `7772fe8e28d2549be76054effcbdb5ef593129aefcfabf8122324256ab78f609` |

The 10 October snapshot was retrieved at `2026-10-10T11:51:51.936218+00:00`. Arsenal–Leeds had started and remains excluded; never reconstruct it after results.

The 17 October snapshot was retrieved at **2026-10-17T09:54:42.103887+00:00** (11:54:42 Swiss time), with manifest written at **09:54:54.787055 UTC**, before the first **11:30 UTC** kickoff. It used the existing alpha=0.10 model specification, **5,380 historical matches**, data cutoff **12 October**. Earlier completed matches may train later forecasts; no match result was used to forecast itself.

Operational provenance:

- Snapshot launch PR: [#80](https://github.com/zee6/FlaretTest1/pull/80).
- Successful snapshot run: [39022856403](https://github.com/zee6/FlaretTest1/actions/runs/39022856403).
- Frozen-evidence commit: `51176f0d50c637973b2372f6524144e51dd33788`.
- Manual workflow restoration/checkpoint PR: [#81](https://github.com/zee6/FlaretTest1/pull/81), master commit `4bc9620b64398c8206df7a8b8ccdd066be6f372e`.
- Current-week historical database SHA256: `1aa8b7f883b46cad55de23e9ebe2332d992757a64fdc3de6fa1b0680793044dd`.
- Raw snapshot SHA256: `a289bb97229aefd829a63cde248c17aa852c5bb7aa3054fd5a4226c976287172`.

Raw live input is in the run's `prospective-live-input` artifact with the existing seven-day retention; do not assume it survives indefinitely. The normalized odds, original probabilities and dated observer files are committed. The snapshot workflow is restored byte-for-byte to its manual-only content from `899e76795a67e478ecec48d89dc8801d28168268`; no weekly schedule was enabled.

## Known gaps

- Draw Possibility remains unavailable for both October slates because its original fixed September historical reference database is unavailable. The generator identifies that reference as the frozen 4 September database. Do not feed it a different database, change the reference or fabricate an original lock.
- The separate legacy `prospective-consensus-movement` replay previously failed downloading expired database artifact/run `33924106948`; its focused tests pass. That failure is distinct from the successful live snapshot workflow, which builds its current database. Do not hide it or describe every historical workflow as green.
- The retained alpha=0.10 model has not established an overall edge over the market. Recency and movement observers retain zero decision weight. Any model activation requires a separate discussion with David.
- The app is native SwiftUI reading Python-generated public data; inference is not migrated to Swift/Core ML. The Results screen currently shows primary/market comparison, not recency or Draw comparisons. Naming remains undecided.

## Resume in this order

1. Pull or clone current `master`, read this checkpoint and inspect later commits. Verify frozen manifest/source identities. Ledger-wide hashes may change only through legitimate append-only records; dated manifests and frozen shadows must remain unchanged.
2. Independently verify Tottenham–Coventry's completed final score, append its settlement with explicit provenance and regenerate the app feed in the same change. If the final is still unavailable, leave it pending.
3. Re-run the explicit current ten-match evaluator and preserve both good and bad findings. Its default intentionally remains the earlier nine-match slate:

   ```bash
   PYTHONPATH=src python -m football1.october_slate_report --slate 2026-10-17-19 --output /tmp/october17-report.json
   PYTHONPATH=src python -m football1.october_slate_report --output /tmp/october10-report.json
   PYTHONPATH=src python -m football1.mobile_results
   PYTHONPATH=src python -m football1.mobile_results --check
   PYTHONPATH=src python -m pytest -q
   ```

4. Remember the 23–25 October primary/movement forecasts already exist. Any further observer work must be prospective, explicitly timestamped and linked to the original source records. Never replace original probabilities or prices. Do not retune after inspecting these outcomes.
5. Review recurring forecast/settlement scheduling separately; it is still manual-only. Keep operational continuity separate from model activation.

Local validation for this update: **345 Python tests passed**; app-feed freshness, independent report/feed probability and one-unit accounting checks, unchanged frozen files/original settlement prefix, all workflow YAML parsing and diff whitespace checks passed. Both dated October CI workflows generate reproducible reports with 90-day artifact retention. Native Swift contract/build/simulator checks run through the existing iPhone workflow when the feed changes. The Results interface itself was merged in PR #79 after native validation and screenshot review.
