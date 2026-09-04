import SwiftUI

struct LiveView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        HSplitView {
            List(model.fixtures, selection: $model.selectedFixtureID) { fixture in
                FixtureListRow(fixture: fixture)
                    .tag(fixture.id)
            }
            .frame(minWidth: 360, idealWidth: 400, maxWidth: 460)

            if let fixture = model.selectedFixture {
                MatchDetailView(fixture: fixture, isPreview: model.isPreview)
                    .frame(minWidth: 560)
            } else {
                ContentUnavailableView("No fixture selected", systemImage: "sportscourt")
            }
        }
    }
}

private struct FixtureListRow: View {
    let fixture: FixtureRow

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text(fixture.homeTeam)
                    .fontWeight(.semibold)
                Text("—")
                    .foregroundStyle(.secondary)
                Text(fixture.awayTeam)
                    .fontWeight(.semibold)
                Spacer()
            }

            HStack(spacing: 12) {
                Text(fixture.kickoff, format: .dateTime.weekday(.abbreviated).hour().minute())
                Text("\(fixture.bookmakerCount) books")
                Spacer()
                if let strongest = fixture.strongestQuote {
                    Text("EV \(strongest.predictedEV.signedPercent1)")
                        .monospacedDigit()
                        .fontWeight(.medium)
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 5)
    }
}

private struct MatchDetailView: View {
    let fixture: FixtureRow
    let isPreview: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(fixture.homeTeam) vs \(fixture.awayTeam)")
                        .font(.largeTitle.weight(.semibold))
                    HStack(spacing: 16) {
                        Text(fixture.kickoff, format: .dateTime.weekday(.wide).day().month(.wide).hour().minute())
                        Text("\(fixture.bookmakerCount) complete 1X2 books")
                        StatusBadge(text: fixture.status)
                    }
                    .foregroundStyle(.secondary)
                }

                if isPreview {
                    Label(
                        "Market figures are from our first live snapshot. Football 1 probabilities below are preview values until the prospective-ledger bridge is connected.",
                        systemImage: "exclamationmark.triangle"
                    )
                    .font(.callout)
                    .padding(12)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                }

                VStack(alignment: .leading, spacing: 12) {
                    Text("1X2 probability and price")
                        .font(.title2.weight(.semibold))
                    ForEach(fixture.quotes) { quote in
                        QuoteRow(quote: quote)
                    }
                }

                if let strongest = fixture.strongestQuote {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Largest current disagreement")
                            .font(.headline)
                        Text("\(strongest.outcome.title): Football 1 \(strongest.football1Probability.percent1) vs market \(strongest.marketProbability.percent1)")
                            .font(.title3)
                        Text("Probability difference \(strongest.probabilityEdge.signedPercent1) · best odds \(strongest.bestOdds.odds2) · model-implied EV \(strongest.predictedEV.signedPercent1)")
                            .foregroundStyle(.secondary)
                            .monospacedDigit()
                        Text("Model disagreement is not the same as a validated betting edge.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(16)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(24)
            .frame(maxWidth: 900, alignment: .leading)
        }
    }
}

private struct QuoteRow: View {
    let quote: OutcomeQuote

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Text(quote.outcome.title)
                    .font(.headline)
                    .frame(width: 70, alignment: .leading)

                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text("Market")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(quote.marketProbability.percent1)
                            .monospacedDigit()
                    }
                    ProgressView(value: quote.marketProbability)

                    HStack {
                        Text("Football 1")
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(quote.football1Probability.percent1)
                            .monospacedDigit()
                    }
                    ProgressView(value: quote.football1Probability)
                }

                VStack(alignment: .trailing, spacing: 5) {
                    Text("Odds \(quote.bestOdds.odds2)")
                        .monospacedDigit()
                    Text("Δ \(quote.probabilityEdge.signedPercent1)")
                        .monospacedDigit()
                    Text("EV \(quote.predictedEV.signedPercent1)")
                        .monospacedDigit()
                        .fontWeight(.semibold)
                }
                .frame(width: 105, alignment: .trailing)
            }
            Divider()
        }
    }
}

struct MispricingView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                Text("Largest model / market disagreements")
                    .font(.largeTitle.weight(.semibold))
                Text("Ranked by model-implied EV at the best quoted price. No threshold here is labelled as a validated strategy.")
                    .foregroundStyle(.secondary)
                    .padding(.bottom, 8)

                ForEach(Array(model.rankedMispricing.enumerated()), id: \.element.fixture.id) { index, item in
                    HStack(alignment: .top, spacing: 16) {
                        Text("\(index + 1)")
                            .font(.title2.monospacedDigit())
                            .frame(width: 32, alignment: .trailing)
                        VStack(alignment: .leading, spacing: 5) {
                            Text("\(item.fixture.homeTeam) — \(item.fixture.awayTeam)")
                                .font(.headline)
                            Text("\(item.quote.outcome.title) · market \(item.quote.marketProbability.percent1) · Football 1 \(item.quote.football1Probability.percent1)")
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 4) {
                            Text(item.quote.predictedEV.signedPercent1)
                                .font(.title2.weight(.semibold).monospacedDigit())
                            Text("EV @ \(item.quote.bestOdds.odds2)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(16)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(24)
            .frame(maxWidth: 1000, alignment: .leading)
        }
    }
}

struct LedgerView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Prospective ledger")
                    .font(.largeTitle.weight(.semibold))
                Text("Predictions are written before kickoff and settlements live separately. Preview rows are shown until the first production ledger is connected.")
                    .foregroundStyle(.secondary)

                ForEach(model.ledger) { row in
                    HStack(spacing: 18) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(row.fixture)
                                .font(.headline)
                            Text(row.timestamp, format: .dateTime.year().month().day().hour().minute())
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text(row.selection)
                            .frame(width: 70)
                        Text("@ \(row.bestOdds.odds2)")
                            .monospacedDigit()
                            .frame(width: 70)
                        Text("EV \(row.predictedEV.signedPercent1)")
                            .monospacedDigit()
                            .frame(width: 90)
                        StatusBadge(text: row.state)
                        Text(row.pnl.map { String(format: "%+.2fu", $0) } ?? "Open")
                            .monospacedDigit()
                            .frame(width: 70, alignment: .trailing)
                    }
                    .padding(14)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                }
            }
            .padding(24)
            .frame(maxWidth: 1100, alignment: .leading)
        }
    }
}

struct ResearchView: View {
    @EnvironmentObject private var model: AppModel
    private let columns = [GridItem(.adaptive(minimum: 250), spacing: 14)]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Research")
                    .font(.largeTitle.weight(.semibold))
                Text("Frozen out-of-sample results. Lower log loss is better; profitable historical tails remain unvalidated prospectively.")
                    .foregroundStyle(.secondary)

                LazyVGrid(columns: columns, alignment: .leading, spacing: 14) {
                    ForEach(model.researchMetrics) { metric in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(metric.title)
                                .font(.headline)
                            Text(metric.value)
                                .font(.title.weight(.semibold).monospacedDigit())
                            Text(metric.detail)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, minHeight: 115, alignment: .topLeading)
                        .padding(16)
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                    }
                }
            }
            .padding(24)
            .frame(maxWidth: 1100, alignment: .leading)
        }
    }
}

struct DataView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Data health")
                    .font(.largeTitle.weight(.semibold))
                Text("Source provenance and pipeline status stay visible so a stale or incompatible feed cannot silently become a model input.")
                    .foregroundStyle(.secondary)

                ForEach(model.dataHealth) { row in
                    HStack(alignment: .top, spacing: 16) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(row.source)
                                .font(.headline)
                            Text(row.detail)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        StatusBadge(text: row.status)
                    }
                    .padding(14)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                }
            }
            .padding(24)
            .frame(maxWidth: 1000, alignment: .leading)
        }
    }
}

private struct StatusBadge: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(.quaternary, in: Capsule())
    }
}
