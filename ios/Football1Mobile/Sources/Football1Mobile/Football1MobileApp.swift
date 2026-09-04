import SwiftUI

@main
struct Football1MobileApp: App {
    var body: some Scene {
        WindowGroup {
            ProspectiveRootView()
        }
    }
}

private struct ProspectiveRootView: View {
    @State private var fixtures = MobilePreviewData.fixtures
    @State private var selectedFixtureID = MobilePreviewData.fixtures[0].id
    @State private var selectedOutcomeID = "H"
    @State private var loadMessage: String?

    private var selectedFixture: MobileFixture {
        fixtures.first { $0.id == selectedFixtureID } ?? fixtures[0]
    }

    var body: some View {
        TabView {
            NavigationStack {
                ProspectiveLiveView(
                    fixtures: fixtures,
                    selectedFixtureID: $selectedFixtureID,
                    selectedOutcomeID: $selectedOutcomeID,
                    loadMessage: loadMessage
                )
                .navigationTitle("Football 1")
                .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem { Label("Live", systemImage: "sportscourt") }

            NavigationStack {
                ProspectiveRealityView()
                    .navigationTitle("Eyes Wide Open")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem { Label("Reality", systemImage: "eye") }

            NavigationStack {
                ProspectiveModelsView()
                    .navigationTitle("Models")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem { Label("Models", systemImage: "square.stack.3d.up") }

            NavigationStack {
                ProspectiveResearchView()
                    .navigationTitle("Research")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem { Label("Research", systemImage: "chart.line.uptrend.xyaxis") }
        }
        .tint(.blue)
        .task {
            await loadProspectiveLedger()
        }
        .onChange(of: selectedFixtureID) { _, _ in
            selectedOutcomeID = selectedFixture.strongestOutcome.id
        }
    }

    @MainActor
    private func loadProspectiveLedger() async {
        do {
            let live = try await MobileLiveData.loadProspectiveFixtures()
            guard !live.isEmpty else {
                loadMessage = "No future locked predictions are currently in the ledger. Showing interface preview data."
                return
            }
            fixtures = live
            selectedFixtureID = live[0].id
            selectedOutcomeID = live[0].strongestOutcome.id
            loadMessage = nil
        } catch {
            loadMessage = "Could not read the public prospective ledger. Showing interface preview data."
        }
    }
}

private struct ProspectiveLiveView: View {
    let fixtures: [MobileFixture]
    @Binding var selectedFixtureID: String
    @Binding var selectedOutcomeID: String
    let loadMessage: String?

    private var fixture: MobileFixture {
        fixtures.first { $0.id == selectedFixtureID } ?? fixtures[0]
    }

    private var outcome: MobileOutcome {
        fixture.outcomes.first { $0.id == selectedOutcomeID } ?? fixture.strongestOutcome
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                ProspectivePrincipleCard()
                SourcePill(isProspective: fixture.isProspective, message: loadMessage)
                fixtureStrip
                matchHeader
                PriceDecisionCard(outcome: outcome)
                outcomeSelector
                ProspectiveModelRoom(outcome: outcome)
                priceReality
                explanation
                Spacer(minLength: 24)
            }
            .padding(16)
        }
        .background(Color(uiColor: .systemGroupedBackground))
    }

    private var fixtureStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(fixtures) { item in
                    Button {
                        selectedFixtureID = item.id
                    } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(item.home)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.primary)
                            Text(item.away)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            HStack {
                                Text(item.kickoff)
                                Spacer(minLength: 6)
                                Text(item.strongestOutcome.ev.f1SignedPercent)
                                    .foregroundStyle(item.strongestOutcome.ev >= 0 ? .blue : .red)
                            }
                            .font(.caption2.weight(.semibold))
                        }
                        .frame(width: 200, alignment: .leading)
                        .padding(12)
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .fill(selectedFixtureID == item.id ? Color.blue.opacity(0.12) : Color(uiColor: .secondarySystemGroupedBackground))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 14)
                                .stroke(selectedFixtureID == item.id ? Color.blue.opacity(0.55) : Color.secondary.opacity(0.16), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var matchHeader: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(fixture.kickoff.uppercased())
                .font(.caption2.weight(.bold))
                .tracking(1)
                .foregroundStyle(.secondary)
            Text("\(fixture.home) vs \(fixture.away)")
                .font(.title2.bold())
            Text(fixture.isProspective
                 ? "\(fixture.bookmakerCount) complete UK books · locked prospective snapshot"
                 : "\(fixture.bookmakerCount) complete UK books · interface preview")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var outcomeSelector: some View {
        VStack(spacing: 10) {
            ForEach(fixture.outcomes) { item in
                Button {
                    selectedOutcomeID = item.id
                } label: {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(item.name)
                                .font(.headline)
                                .foregroundStyle(.primary)
                            Text("Football 1 \(item.football1.f1Percent) · Market \(item.market.f1Percent)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 3) {
                            Text(item.odds.f1Odds)
                                .font(.headline.monospacedDigit())
                                .foregroundStyle(.primary)
                            Text("EV \(item.ev.f1SignedPercent)")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(item.ev >= 0 ? .blue : .red)
                        }
                    }
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: 15)
                            .fill(selectedOutcomeID == item.id ? Color.blue.opacity(0.10) : Color(uiColor: .secondarySystemGroupedBackground))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 15)
                            .stroke(selectedOutcomeID == item.id ? Color.blue.opacity(0.55) : Color.secondary.opacity(0.14), lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var priceReality: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Price reality", systemImage: "scalemass")
                .font(.headline)
            PriceFact(label: "Available price", value: outcome.odds.f1Odds)
            PriceFact(label: "Break-even probability", value: outcome.breakEven.f1Percent)
            PriceFact(label: "Football 1 probability", value: outcome.football1.f1Percent)
            PriceFact(label: "Model vs market", value: outcome.edge.f1SignedPercent)
            PriceFact(label: "Model-implied EV", value: outcome.ev.f1SignedPercent, emphasized: true, positive: outcome.ev >= 0)
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }

    private var explanation: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text("WHY FOOTBALL 1 SAYS THIS")
                .font(.caption2.weight(.bold))
                .tracking(1)
                .foregroundStyle(.secondary)
            Text("At odds of \(outcome.odds.f1Odds), \(outcome.name) needs \(outcome.breakEven.f1Percent) to break even. Football 1's probability is \(outcome.football1.f1Percent). The result may still win or lose; the decision question is whether the price compensates for that uncertainty.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            if fixture.isProspective {
                Text("This probability was locked before kickoff. Positive model-implied EV is descriptive; no betting threshold has yet earned prospective promotion.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct ProspectivePrincipleCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("FOUNDING PRINCIPLE")
                .font(.caption2.weight(.bold))
                .tracking(1.2)
                .foregroundStyle(.secondary)
            Text("Winning is an outcome.")
                .font(.title2.bold())
            Text("Making money is a relationship between probability and price.")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct SourcePill: View {
    let isProspective: Bool
    let message: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 7) {
                Image(systemName: isProspective ? "checkmark.seal" : "testtube.2")
                Text(isProspective ? "PROSPECTIVE · LOCKED BEFORE KICKOFF" : "INTERFACE PREVIEW")
            }
            .font(.caption2.weight(.bold))
            .foregroundStyle(isProspective ? Color.green : Color.orange)
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(Capsule().fill((isProspective ? Color.green : Color.orange).opacity(0.12)))

            if let message {
                Text(message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private struct PriceDecisionCard: View {
    let outcome: MobileOutcome

    private var presentation: (label: String, color: Color, title: String, detail: String) {
        if outcome.ev < 0 {
            let title = outcome.football1 >= 0.60 ? "Strong prediction. Poor price." : "Price below Football 1 fair value"
            return (
                "BELOW FAIR",
                .red,
                title,
                "The offered odds require \(outcome.breakEven.f1Percent) to break even, above Football 1's \(outcome.football1.f1Percent) estimate."
            )
        }
        return (
            "ABOVE FAIR",
            .blue,
            "The price clears the model's break-even test",
            "Football 1's probability is above the break-even probability at this quoted price. This is a price observation, not a validated betting signal."
        )
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Text("EYES WIDE OPEN")
                    .font(.caption2.weight(.bold))
                    .tracking(1)
                    .foregroundStyle(.secondary)
                Text(presentation.title)
                    .font(.headline)
                Text(presentation.detail)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Text(presentation.label)
                .font(.caption.weight(.heavy))
                .foregroundStyle(presentation.color)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(Capsule().fill(presentation.color.opacity(0.12)))
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct ProspectiveModelRoom: View {
    let outcome: MobileOutcome

    private var rows: [(String, Double)] {
        var result: [(String, Double)] = [("Market", outcome.market)]
        if outcome.elo.isFinite { result.append(("Elo", outcome.elo)) }
        if outcome.poisson.isFinite { result.append(("Poisson", outcome.poisson)) }
        result.append(("Football 1", outcome.football1))
        return result
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Model room", systemImage: "square.stack.3d.up")
                .font(.headline)
            ForEach(rows, id: \.0) { row in
                HStack(spacing: 10) {
                    Text(row.0)
                        .font(.caption)
                        .frame(width: 72, alignment: .leading)
                    GeometryReader { proxy in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Color.secondary.opacity(0.12))
                            Capsule().fill(Color.blue.opacity(0.65))
                                .frame(width: proxy.size.width * min(max(row.1, 0), 1))
                        }
                    }
                    .frame(height: 8)
                    Text(row.1.f1Percent)
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .frame(width: 48, alignment: .trailing)
                }
            }
            if !outcome.elo.isFinite || !outcome.poisson.isFinite {
                Text("The prospective ledger currently carries the market anchor and Football 1 tightener. Independent Elo and Poisson probabilities remain context modules and are not fabricated here.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct PriceFact: View {
    let label: String
    let value: String
    var emphasized = false
    var positive = false

    var body: some View {
        HStack {
            Text(label).foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .monospacedDigit()
                .fontWeight(emphasized ? .bold : .semibold)
                .foregroundStyle(emphasized ? (positive ? Color.blue : Color.red) : Color.primary)
        }
        .font(.subheadline)
    }
}

private struct ProspectiveRealityView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                ProspectivePrincipleCard()
                RealityLesson(kicker: "LIKELY WINNER", title: "Can still be a poor purchase", detail: "Probability answers what is likely to happen. Price determines what you are being paid for taking the risk.")
                RealityLesson(kicker: "UNLIKELY OUTCOME", title: "Can still be correctly priced — or cheap", detail: "Losing often is compatible with positive expectancy when the price more than compensates for the low probability.")
                RealityLesson(kicker: "RESULT ≠ PROCESS", title: "Judge the decision at kickoff", detail: "A good decision can lose. A bad decision can win. Football 1 keeps the pre-match price judgement separate from the final score.")
            }
            .padding(16)
        }
        .background(Color(uiColor: .systemGroupedBackground))
    }
}

private struct RealityLesson: View {
    let kicker: String
    let title: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(kicker).font(.caption2.bold()).tracking(1).foregroundStyle(.secondary)
            Text(title).font(.title3.bold())
            Text(detail).font(.subheadline).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct ProspectiveModelsView: View {
    private let modules = [
        ("Market", "Collective information + price", "ANCHOR"),
        ("Football 1 tightener", "Conservative residual adjustment", "PROSPECTIVE"),
        ("Elo", "Underlying team strength", "CONTEXT"),
        ("Poisson", "Score distribution / draw shape", "CONTEXT"),
        ("Home / Away", "Venue-role behaviour", "CONTEXT"),
        ("Head-to-head", "Pair-specific history", "NO WEIGHT")
    ]

    var body: some View {
        List {
            Section {
                Text("Every model gets an opinion. Not every model earns the right to move the probability.")
                    .font(.headline)
            }
            Section("Modules") {
                ForEach(Array(modules.enumerated()), id: \.offset) { _, item in
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(item.0).fontWeight(.semibold)
                            Text(item.1).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text(item.2)
                            .font(.caption2.bold())
                            .foregroundStyle(item.2 == "NO WEIGHT" ? Color.red : (item.2 == "PROSPECTIVE" ? Color.orange : Color.blue))
                    }
                    .padding(.vertical, 3)
                }
            }
        }
    }
}

private struct ProspectiveResearchView: View {
    var body: some View {
        List {
            Section("Frozen OOS results") {
                researchRow("Market log loss", "0.960279", "Bet365 de-vigged baseline")
                researchRow("Elo top-pick accuracy", "53.45%", "2,245 / 4,200 correct")
                researchRow("Blind Elo betting ROI", "−4.16%", "Being right did not make the price good")
                researchRow("Residual slant log loss", "0.962730", "Still worse than the market")
            }
            Section("Prospective rule") {
                Text("Predictions are frozen before kickoff. Results settle later. Positive model-implied EV is observed, but no threshold is promoted after inspecting outcomes.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func researchRow(_ title: String, _ value: String, _ detail: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(title)
                Spacer()
                Text(value).fontWeight(.bold).monospacedDigit()
            }
            Text(detail).font(.caption).foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}
