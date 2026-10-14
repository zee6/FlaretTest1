import SwiftUI

struct ResultsDashboard: View {
    @State private var feed: ResultsFeed?
    @State private var selectedBatchID: String?
    @State private var isLoading = false
    @State private var loadFailed = false

    private var batch: ResultsBatch? {
        feed?.batches.first { $0.id == selectedBatchID } ?? feed?.batches.first
    }

    var body: some View {
        ZStack {
            F1Background()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 18) {
                    BrandHeader(eyebrow: "Results", title: "The record, kept honest", subtitle: "Frozen forecasts. Recorded outcomes.")
                        .padding(.top, 8)
                    if ResultsFeed.usesBundledPreview {
                        Text("BUNDLED SNAPSHOT · SIMULATOR PREVIEW")
                            .font(.caption2.bold()).foregroundStyle(F1Theme.caution)
                    }
                    if isLoading && feed == nil {
                        ProgressView("Loading recorded results…")
                            .frame(maxWidth: .infinity).padding(.vertical, 40)
                    }
                    if loadFailed {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Results could not be loaded").font(.headline)
                            Text(feed == nil ? "Check your connection, then try again." : "Showing the previously loaded snapshot. Refresh to check for newer settlements.")
                                .font(.subheadline).foregroundStyle(F1Theme.secondary)
                            Button("Try again") { Task { await load() } }.disabled(isLoading)
                        }.f1Card()
                    }
                    if let feed {
                        if let batch {
                            batchPicker(feed)
                            summary(batch)
                            officialPortfolio
                            scoring(batch)
                            diagnostic(batch)
                            Text("MATCH RECORD").font(.caption2.bold()).tracking(1.2).foregroundStyle(F1Theme.accent)
                            Text("Tap a match for its original probabilities and recorded price.")
                                .font(.caption).foregroundStyle(F1Theme.secondary)
                            ForEach(batch.matches) { match in ResultsMatchCard(match: match) }
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Forecasts frozen \(ResultsDate.timestamp(batch.frozenAtUtc))")
                                if let recorded = feed.lastSettlementAtUtc {
                                    Text("Latest ledger settlement \(ResultsDate.timestamp(recorded))")
                                }
                                Text("Recorded results, not a live score service. Unresolved matches are excluded from every score and P&L total.")
                                Button("Refresh results") { Task { await load() } }.disabled(isLoading)
                            }.font(.caption).foregroundStyle(F1Theme.secondary)
                        } else {
                            Text("No prospective forecast batches have been recorded yet.").f1Card()
                        }
                    }
                    Spacer(minLength: 24)
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .refreshable { await load() }
        }
        .task { if feed == nil { await load() } }
    }

    @MainActor
    private func load() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let updated = try await ResultsFeed.load()
            feed = updated
            if !updated.batches.contains(where: { $0.id == selectedBatchID }) { selectedBatchID = updated.batches.first?.id }
            loadFailed = false
        } catch is CancellationError {
            // View dismissal is not a data error; a later appearance retries.
        } catch {
            loadFailed = true
        }
    }

    private func batchPicker(_ feed: ResultsFeed) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("RECORDED SLATE").font(.caption2.bold()).foregroundStyle(F1Theme.secondary)
            Picker("Recorded slate", selection: $selectedBatchID) {
                ForEach(feed.batches) { batch in
                    Text(batch.dateLabel).tag(Optional(batch.id))
                }
            }
            .pickerStyle(.menu).labelsHidden().tint(F1Theme.accent)
        }
    }

    private func summary(_ batch: ResultsBatch) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(batch.settledCount == 0 ? "AWAITING RESULTS" : batch.pendingCount == 0 ? "SLATE COMPLETE" : "PARTIAL RESULTS")
                .font(.caption2.bold()).tracking(1.0).foregroundStyle(F1Theme.accent)
            Text("\(batch.settledCount) of \(batch.matches.count) settled")
                .font(.system(size: 30, weight: .bold, design: .rounded)).monospacedDigit()
            Text("\(batch.pendingCount) unresolved · same settled sample for model and market")
                .font(.caption).foregroundStyle(F1Theme.secondary)
        }.f1Card(strong: true)
    }

    private var officialPortfolio: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("OFFICIAL PORTFOLIO · INACTIVE").font(.caption2.bold()).tracking(0.7).foregroundStyle(F1Theme.secondary)
            Text("0 bets · 0 staked · 0 P&L").font(.headline)
            Text("No betting rule has been prospectively validated.").font(.caption).foregroundStyle(F1Theme.secondary)
        }.f1Card()
    }

    private func scoring(_ batch: ResultsBatch) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Model versus market").font(.headline)
            Grid(alignment: .trailing, horizontalSpacing: 16, verticalSpacing: 10) {
                GridRow {
                    Text("Lower is better").gridColumnAlignment(.leading)
                    Text("Football 1")
                    Text("Market")
                }.foregroundStyle(F1Theme.secondary)
                scoreRow("Log loss", batch.scoring.modelLogLoss, batch.scoring.marketLogLoss)
                scoreRow("Brier", batch.scoring.modelBrier, batch.scoring.marketBrier)
            }.font(.caption).monospacedDigit()
            if let model = batch.scoring.modelLogLoss, let market = batch.scoring.marketLogLoss {
                Text(model > market ? "Football 1 trails the market on log loss in this sample." : model < market ? "Football 1 leads the market on log loss in this sample." : "Football 1 matches the market on log loss in this sample.")
                    .font(.subheadline).foregroundStyle(model > market ? F1Theme.caution : F1Theme.text)
            } else {
                Text("Probability scores appear after the first settlement.").font(.caption).foregroundStyle(F1Theme.secondary)
            }
            Text("Market = bookmaker probabilities after margin removal. These observations do not establish a betting edge.")
                .font(.caption).foregroundStyle(F1Theme.secondary)
        }.f1Card()
    }

    private func scoreRow(_ title: String, _ model: Double?, _ market: Double?) -> some View {
        GridRow {
            Text(title)
            Text(model.map { String(format: "%.4f", $0) } ?? "—")
            Text(market.map { String(format: "%.4f", $0) } ?? "—")
        }
    }

    private func diagnostic(_ batch: ResultsBatch) -> some View {
        let values = batch.diagnostic
        return VStack(alignment: .leading, spacing: 10) {
            Text("HYPOTHETICAL · ONE UNIT PER MATCH").font(.caption2.bold()).tracking(0.7).foregroundStyle(F1Theme.caution)
            Text(String(format: "%+.2f units", values.pnlUnits))
                .font(.system(size: 28, weight: .bold, design: .rounded)).monospacedDigit()
                .foregroundStyle(values.pnlUnits < 0 ? F1Theme.negative : F1Theme.text)
            Text("\(values.stakeUnits) units staked · \(values.wins) won · \(values.stakeUnits - values.wins) lost")
                .font(.subheadline)
            Text("ROI \(values.roi.map { String(format: "%+.1f%%", $0 * 100) } ?? "—") · Max drawdown \(String(format: "%.2f", values.maxDrawdownUnits)) units")
                .font(.caption).foregroundStyle(F1Theme.secondary)
            Text("One imaginary unit on the highest recorded EV outcome in every settled match, including negative EV. Gross quoted-price P&L; execution and commission are not accounted for. This is a diagnostic, not a betting recommendation.")
                .font(.caption).foregroundStyle(F1Theme.secondary)
            Text("Drawdown groups simultaneous kickoffs; unresolved matches contribute nothing.")
                .font(.caption).foregroundStyle(F1Theme.secondary)
        }.f1Card()
    }
}

private struct ResultsMatchCard: View {
    let match: ResultsMatch

    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 12) {
                Text(ResultsDate.timestamp(match.kickoffUtc)).font(.caption).foregroundStyle(F1Theme.secondary)
                Grid(alignment: .trailing, horizontalSpacing: 12, verticalSpacing: 10) {
                    GridRow {
                        Text("At the freeze").gridColumnAlignment(.leading)
                        Text("Home"); Text("Draw"); Text("Away")
                    }.foregroundStyle(F1Theme.secondary)
                    probabilityRow("Football 1", match.modelProbability)
                    probabilityRow("Market", match.marketProbability)
                    GridRow {
                        Text("Decimal odds")
                        Text(match.odds.home.f1Odds); Text(match.odds.draw.f1Odds); Text(match.odds.away.f1Odds)
                    }
                }.font(.caption).monospacedDigit()
                Text("Hypothetical selection: \(match.selectionName) at \(match.odds.value(for: match.selection).f1Odds) · EV \(match.predictedEv.f1SignedPercent)")
                    .font(.caption).foregroundStyle(F1Theme.secondary)
                if let result = match.settlement {
                    Text("One-unit P&L: \(String(format: "%+.2f", result.pnlUnits)) · recorded \(ResultsDate.timestamp(result.recordedAtUtc))")
                        .font(.caption).foregroundStyle(result.pnlUnits < 0 ? F1Theme.negative : F1Theme.text)
                } else {
                    Text("No final score recorded. Excluded from scoring and P&L.")
                        .font(.caption).foregroundStyle(F1Theme.secondary)
                }
            }.padding(.top, 12)
        } label: {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(match.home).font(.subheadline.weight(.semibold))
                    Text(match.away).font(.subheadline.weight(.semibold))
                    Text(match.settlement == nil ? "UNRESOLVED" : "FINAL SCORE RECORDED")
                        .font(.caption2).foregroundStyle(F1Theme.secondary)
                }
                Spacer(minLength: 2)
                if let result = match.settlement {
                    VStack(spacing: 5) {
                        Text("\(result.homeScore)"); Text("\(result.awayScore)")
                    }.font(.subheadline.bold()).monospacedDigit()
                } else {
                    Text("—").foregroundStyle(F1Theme.secondary)
                }
            }.foregroundStyle(F1Theme.text)
        }.f1Card()
    }

    private func probabilityRow(_ title: String, _ values: ResultsTriple) -> some View {
        GridRow {
            Text(title)
            Text(values.home.f1Percent); Text(values.draw.f1Percent); Text(values.away.f1Percent)
        }
    }
}
