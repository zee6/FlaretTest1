# Football 1 macOS

Native SwiftUI research interface for Football 1.

## Open in Xcode

1. On the Mac, clone or pull `zee6/FlaretTest1`.
2. In Finder, open `macos/Football1App/Football1.xcodeproj` with Xcode.
3. Select the `Football1` scheme and **My Mac**.
4. Press Run (`⌘R`).

This is a real macOS application target with bundle identifier `com.riskbrain.Football1`. No API key is required to launch this first shell.

Do **not** run `Package.swift` for the app UI. The Swift package remains only as a lightweight source/build convenience; the Xcode project is the canonical way to run the macOS application.

## Current data boundary

The UI currently contains:

- real fixture names and market consensus values sampled from Football 1's first successful live Odds API snapshot;
- clearly marked preview Football 1 probabilities for interface development;
- frozen historical research metrics from Phase 1C;
- preview prospective-ledger rows.

It does **not** run the model independently in Swift. The next integration step is a read-only bridge from the Python-generated prospective ledger/live snapshot into these Swift models. The Python research pipeline remains the source of truth.

## CI build

GitHub Actions validates the real app bundle with `xcodebuild` and checks that the generated `.app` contains the expected bundle identifier.
