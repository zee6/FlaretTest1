# Product naming and migration notes

Recorded 10 October 2026. **Football 1 is a working title.** David wants an eventual coherent project-wide rename; no replacement name has been selected and no rename is performed by this change.

Candidates retained for future consideration: **Fairline, MatchLens, Touchline, TrueLine**. These are brainstorming candidates only. Trademark, domain and App Store availability have not been checked.

## Inventory from the current repository

| Surface | Current locations / identifiers | Migration requirement |
|---|---|---|
| Web display | `web/index.html`, `web/app.js`, `web/README.md` | Page title, brand, accessibility labels and explanatory copy need the chosen product name. Centralize repeated display text before broad replacement. |
| iPhone display | `ios/Football1Mobile/Sources/Football1Mobile/`, Xcode `PRODUCT_NAME` and `CFBundleDisplayName` | Update visible text and app display/product names together; retain the current interface design. |
| Mac display | `macos/Football1App/Sources/Football1App/`, Xcode `PRODUCT_NAME` and `CFBundleDisplayName` | Update text and app product metadata together. |
| Apple identity | `com.riskbrain.Football1Mobile`, `com.riskbrain.Football1` | Treat separately from branding. Preserve existing app identity unless a deliberate migration is agreed, to avoid breaking update continuity. |
| Build topology | Xcode project/scheme/source paths; `macos/Football1App/Package.swift` | Rename only in a coordinated change, including references, schemes and artifact checks. |
| Python | `src/football1`, imports, `pyproject.toml` package and `football1-*` entry points | A technical rename needs compatibility aliases or an explicit migration for commands and imports. Product branding does not require a rushed package rename. |
| GitHub/data links | `zee6/FlaretTest1`; hardcoded `raw.githubusercontent.com` URLs in iPhone `Models.swift` and `EloResearch.swift` | Verify actual data endpoints and installed-client compatibility before a repository rename; do not assume redirects solve every consumer. |
| CI and docs | `.github/workflows/`, README files and current project state | Update path filters, working directories, schemes, CLI calls, `.app` names and output checks consistently. |
| Frozen research identity | Prospective ledgers, manifests, hashes, model IDs, historical results | Preserve historical bytes and identifiers. Add a name/alias mapping outside the hashed records instead of rewriting evidence. |

## Migration sequence

1. Choose and check a name. Record product name separately from package, model, repository and bundle identifiers.
2. Introduce central display-name configuration for each client, retaining the working title as the default until the name is agreed.
3. Update visible branding coherently. Inventory remaining old strings and classify them as compatibility identity, frozen evidence, or missed display text.
4. Perform any technical identifier/repository migration separately, with explicit compatibility paths and rollback.
5. Run Python tests and existing iPhone/macOS CI builds; inspect web and native visible text. Check both data endpoints and that existing ledgers retain exactly the same bytes and hashes.

The finished product should have one clear public name. Preserving old technical identifiers where necessary for compatibility is deliberate, not incomplete branding.
