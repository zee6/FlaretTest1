import SwiftUI

struct ContentView: View {
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
                LiveDashboardView(
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
                EyesWideOpenView()
                    .navigationTitle("Eyes Wide Open")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem { Label("Reality", systemImage: "eye") }

            NavigationStack {
                ModelStatusView()
                    .navigationTitle("Models")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem { Label("Models", systemImage: "square.stack.3d.up") }

            NavigationStack {
                EloResearchDashboard(
                    fixtures: fixtures,
                    selectedFixtureID: selectedFixtureID
                )
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

private struct LiveDashboardView: View {
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
                PrincipleCard()
                SourcePill(isProspective: fixture.isProspective, message: loadMessage)
                fixtureStrip
                matchHeader
                SelectedOutcomeCard(outcome: outcome)
                PlainEnglishDecisionCard(outcome: outcome)
                outcomeSelector
                ProbabilityCard(outcome: outcome)
                PriceRealityCard(outcome: outcome)
                ExplanationCard(fixture: fixture, outcome: outcome)
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
                                Text("Best model/price gap \(item.strongestOutcome.ev.f1SignedPercent)")
                                    .foregroundStyle(.secondary)
                            }
                            .font(.caption2.weight(.semibold))
                        }
                        .frame(width: 224, alignment: .leading)
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
                 ? "\(fixture.bookmakerCount) complete UK bookmaker prices · prediction locked before kickoff"
                 : "\(fixture.bookmakerCount) complete UK bookmaker prices · interface preview")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var outcomeSelector: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Choose an outcome")
                .font(.headline)
            ForEach(fixture.outcomes) { item in
                Button {
                    selectedOutcomeID = item.id
                } label: {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(item.name)
                                .font(.headline)
                                .foregroundStyle(.primary)
                            Text("Football 1: \(item.football1.f1Percent) · Market: \(item.market.f1Percent)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 3) {
                            Text("Odds \(item.odds.f1Odds)")
                                .font(.headline.monospacedDigit())
                                .foregroundStyle(.primary)
                            Text("Price gap \(item.ev.f1SignedPercent)")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
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
}

private struct PrincipleCard: View {
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
                Text(isProspective ? "REAL DATA · LOCKED BEFORE KICKOFF" : "INTERFACE PREVIEW")
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

private struct SelectedOutcomeCard: View {
    let outcome: MobileOutcome

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("YOU ARE LOOKING AT")
                .font(.caption2.bold())
                .tracking(1)
                .foregroundStyle(.secondary)
            Text(outcome.name)
                .font(.title.bold())
            Text("Every probability and price below refers to \(outcome.name).")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color.blue.opacity(0.08)))
    }
}

private struct PlainEnglishDecisionCard: View {
    let outcome: MobileOutcome

    private var fairOdds: Double { 1.0 / outcome.football1 }

    private var title: String {
        outcome.ev >= 0
            ? "\(outcome.name): the quoted price is above Football 1's fair price"
            : "\(outcome.name): the quoted price is below Football 1's fair price"
    }

    private var detail: String {
        if outcome.ev >= 0 {
            return "Football 1 estimates \(outcome.name) at \(outcome.football1.f1Percent). Odds of \(outcome.odds.f1Odds) only need \(outcome.breakEven.f1Percent) to break even, so the quoted price is more generous than the model's estimate."
        }
        return "Football 1 estimates \(outcome.name) at \(outcome.football1.f1Percent). Odds of \(outcome.odds.f1Odds) need \(outcome.breakEven.f1Percent) to break even, so the quoted price asks more of \(outcome.name) than the model expects."
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("WHAT THIS MEANS")
                .font(.caption2.bold())
                .tracking(1)
                .foregroundStyle(.secondary)
            Text(title)
                .font(.headline)
            Text(detail)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text("Football 1 fair odds for \(outcome.name): \(fairOdds.f1Odds)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct ProbabilityCard: View {
    let outcome: MobileOutcome

    private var rows: [(String, Double)] {
        var result: [(String, Double)] = [("Market estimate", outcome.market)]
        if outcome.elo.isFinite { result.append(("Elo context", outcome.elo)) }
        if outcome.poisson.isFinite { result.append(("Poisson context", outcome.poisson)) }
        result.append(("Football 1", outcome.football1))
        return result
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("How likely is \(outcome.name)?")
                .font(.headline)
            ForEach(rows, id: \.0) { row in
                HStack(spacing: 10) {
                    Text(row.0)
                        .font(.caption)
                        .frame(width: 100, alignment: .leading)
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
                Text("Elo and Poisson remain research context. They are not inserted into this live row unless a prospective export supplies them.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct PriceRealityCard: View {
    let outcome: MobileOutcome

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("\(outcome.name): probability and price")
                .font(.headline)
            PriceLine(label: "\(outcome.name) quoted odds", value: outcome.odds.f1Odds)
            PriceLine(label: "\(outcome.name) break-even chance", value: outcome.breakEven.f1Percent)
            PriceLine(label: "Football 1 chance of \(outcome.name)", value: outcome.football1.f1Percent)
            PriceLine(label: "Football 1 minus market", value: outcome.edge.f1SignedPercent)
            PriceLine(label: "Model-implied return at this price", value: outcome.ev.f1SignedPercent, emphasized: true)
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct PriceLine: View {
    let label: String
    let value: String
    var emphasized = false

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer(minLength: 12)
            Text(value)
                .monospacedDigit()
                .fontWeight(emphasized ? .bold : .semibold)
        }
        .font(.subheadline)
    }
}

private struct ExplanationCard: View {
    let fixture: MobileFixture
    let outcome: MobileOutcome
    @State private var showTechnical = false

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text("IN PLAIN ENGLISH")
                .font(.caption2.weight(.bold))
                .tracking(1)
                .foregroundStyle(.secondary)
            Text("Football 1 thinks \(outcome.name) happens about \(outcome.football1.f1Percent) of the time. At the quoted odds of \(outcome.odds.f1Odds), \(outcome.name) would need to happen \(outcome.breakEven.f1Percent) of the time just to break even over many similar bets.")
                .font(.subheadline)
            Text(outcome.ev >= 0
                 ? "On Football 1's numbers, the price is on the generous side. That does not mean \(outcome.name) is likely to win this match."
                 : "On Football 1's numbers, the price is too short. \(outcome.name) can still win this match; the question here is the price, not the result.")
                .font(.subheadline.weight(.semibold))

            DisclosureGroup("Show technical detail", isExpanded: $showTechnical) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Market probability for \(outcome.name): \(outcome.market.f1Percent)")
                    Text("Football 1 minus market: \(outcome.edge.f1SignedPercent)")
                    Text("Model-implied EV at quoted odds: \(outcome.ev.f1SignedPercent)")
                    if fixture.isProspective {
                        Text("This Football 1 probability was locked before kickoff. No betting threshold has yet earned prospective promotion.")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.top, 6)
            }
            .font(.caption.weight(.semibold))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct EyesWideOpenView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                PrincipleCard()
                LessonCard(
                    kicker: "LIKELY WINNER",
                    title: "Can still be a bad price",
                    detail: "A team can be very likely to win and still be a poor purchase if the odds demand an even higher win rate."
                )
                LessonCard(
                    kicker: "UNLIKELY WINNER",
                    title: "Can still be a fair price",
                    detail: "An outsider can lose most of the time and still be fairly priced if the odds compensate for those frequent losses."
                )
                LessonCard(
                    kicker: "RESULT ≠ DECISION",
                    title: "Judge the decision at kickoff",
                    detail: "A sensible decision can lose. A poor decision can win. Football 1 keeps the pre-match price judgement separate from the final score."
                )
            }
            .padding(16)
        }
        .background(Color(uiColor: .systemGroupedBackground))
    }
}

private struct LessonCard: View {
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

private struct ModelStatusView: View {
    private let modules = [
        ("Market", "The bookmaker market, converted into probabilities after removing the built-in margin.", "ANCHOR"),
        ("Football 1", "A deliberately small adjustment to the market estimate. It is being tested prospectively.", "TESTING"),
        ("Elo", "A simple running measure of team strength based only on match results.", "CONTEXT"),
        ("Poisson", "A model of likely scorelines and the shape of the draw probability.", "CONTEXT"),
        ("Home / Away", "Checks whether a team's home and away behaviour adds useful information.", "CONTEXT"),
        ("Head-to-head", "Past meetings between the same two clubs. It currently receives no predictive weight.", "NO WEIGHT")
    ]

    var body: some View {
        List {
            Section {
                Text("Every model is allowed to provide evidence. Only models that prove they improve unseen predictions are allowed to move the final probability.")
                    .font(.headline)
            }
            Section("What each model does") {
                ForEach(Array(modules.enumerated()), id: \.offset) { _, item in
                    VStack(alignment: .leading, spacing: 5) {
                        HStack {
                            Text(item.0).fontWeight(.semibold)
                            Spacer()
                            Text(item.2)
                                .font(.caption2.bold())
                                .foregroundStyle(item.2 == "NO WEIGHT" ? Color.red : (item.2 == "TESTING" ? Color.orange : Color.blue))
                        }
                        Text(item.1)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }
}
