# Football 1 for iPhone

Native SwiftUI interface for the Football 1 research product.

## Open in Xcode

Open:

`ios/Football1Mobile/Football1Mobile.xcodeproj`

Choose the **Football1Mobile** scheme and an iPhone simulator (or your connected iPhone), then press **Command-R**.

Use **Integrate → Pull** on `master` to get merged updates before running.

Match and Reality load future, pre-kickoff forecasts from the public prospective ledger. When no future locked fixtures remain, they show an empty state. Research remains an observer; the app does not refit forecasts or activate a betting policy.

The **Results** tab loads `prospective/mobile_results.json` from this repository's `master` branch. It opens on the latest frozen batch and offers earlier batches in the slate menu. Tap a match for its final score, original Home / Draw / Away probabilities, recorded odds and hypothetical one-unit result. Pull to refresh or use **Refresh results**.

Results compare the primary Football 1 model with the margin-free market on the same settled sample. The hypothetical max-EV-every-match diagnostic is gross quoted-price P&L, including selections with negative EV. Its stakes and P&L are separate from the official inactive zero-bet portfolio. Unresolved matches are excluded, and probability scores/ROI remain unavailable until a result is recorded. This is a recorded-results viewer, not a live score service. Recency and Draw shadows remain in the research reports; they are not added to this screen.

The app reads public repository data; it contains no bookmaker credentials and does not make bookmaker API calls.

## Updating recorded results

After appending verified settlements or new frozen predictions, regenerate the derived feed in the same change:

```bash
python -m football1.mobile_results
python -m football1.mobile_results --check
```

The exporter checks original content hashes, prediction/result links, timing, probability scores and settlement arithmetic. CI rejects a stale feed. No prediction is refitted or source-ledger byte changed by the exporter. Drawdown groups simultaneous kickoffs; it is a units-based diagnostic, not a bankroll simulation.

CI compiles the Swift decoder, exercises valid/pending/empty/malformed feeds, builds the iPhone simulator app and captures its Results screen. For a repeatable offline simulator preview, add `--results-preview` to the scheme's launch arguments in a **Debug** build. This opens Results using the bundled feed and displays a **BUNDLED SNAPSHOT · SIMULATOR PREVIEW** label. Remove the argument to load current published results. Release builds ignore this argument; failed network loads show an error and retry control rather than substituting preview data.

Bundle identifier: `com.riskbrain.Football1Mobile`

Minimum iOS: 17.0
