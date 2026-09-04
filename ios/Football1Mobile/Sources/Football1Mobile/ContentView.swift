import SwiftUI

private enum F1Theme {
    static let background = Color(red: 0.025, green: 0.032, blue: 0.050)
    static let backgroundLift = Color(red: 0.045, green: 0.055, blue: 0.080)
    static let panel = Color.white.opacity(0.060)
    static let panelStrong = Color.white.opacity(0.095)
    static let stroke = Color.white.opacity(0.10)
    static let text = Color.white
    static let secondary = Color.white.opacity(0.58)
    static let tertiary = Color.white.opacity(0.34)
    static let accent = Color(red: 0.42, green: 0.72, blue: 1.0)
    static let accentSoft = Color(red: 0.30, green: 0.55, blue: 0.92)
    static let positive = Color(red: 0.39, green: 0.88, blue: 0.67)
    static let caution = Color(red: 0.98, green: 0.72, blue: 0.32)
    static let negative = Color(red: 1.0, green: 0.43, blue: 0.48)
}

struct ContentView: View {
    @State private var fixtures = MobilePreviewData.fixtures
    @State private var selectedFixtureID = MobilePreviewData.fixtures[0].id
    @State private var selectedOutcomeID = MobilePreviewData.fixtures[0].mostLikelyOutcome.id
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
                .toolbar(.hidden, for: .navigationBar)
            }
            .tabItem { Label("Match", systemImage: "scope") }

            NavigationStack {
                RealityView(
                    fixtures: fixtures,
                    selectedFixtureID: $selectedFixtureID
                )
                .toolbar(.hidden, for: .navigationBar)
            }
            .tabItem { Label("Reality", systemImage: "eye") }

            NavigationStack {
                ModelStatusView()
                    .toolbar(.hidden, for: .navigationBar)
            }
            .tabItem { Label("Models", systemImage: "circle.hexagongrid") }

            NavigationStack {
                EloResearchDashboard(
                    fixtures: fixtures,
                    selectedFixtureID: selectedFixtureID
                )
                .navigationTitle("Research")
                .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem { Label("Research", systemImage: "chart.xyaxis.line") }
        }
        .tint(F1Theme.accent)
        .preferredColorScheme(.dark)
        .toolbarBackground(F1Theme.background.opacity(0.96), for: .tabBar)
        .toolbarBackground(.visible, for: .tabBar)
        .task {
            await loadProspectiveLedger()
        }
        .onChange(of: selectedFixtureID) { _, _ in
            selectedOutcomeID = selectedFixture.mostLikelyOutcome.id
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
            selectedOutcomeID = live[0].mostLikelyOutcome.id
            loadMessage = nil
        } catch {
            loadMessage = "Could not read the public prospective ledger. Showing interface preview data."
        }
    }
}

private struct F1Background: View {
    var body: some View {
        ZStack {
            F1Theme.background
            LinearGradient(
                colors: [
                    F1Theme.accent.opacity(0.10),
                    Color.clear,
                    Color.purple.opacity(0.045)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        }
        .ignoresSafeArea()
    }
}

private struct BrandHeader: View {
    let eyebrow: String
    let title: String
    let subtitle: String?

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(eyebrow.uppercased())
                    .font(.caption2.weight(.bold))
                    .tracking(1.7)
                    .foregroundStyle(F1Theme.accent)
                Text(title)
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .foregroundStyle(F1Theme.text)
                if let subtitle {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(F1Theme.secondary)
                }
            }
            Spacer()
            ZStack {
                Circle()
                    .fill(F1Theme.accent.opacity(0.13))
                    .frame(width: 42, height: 42)
                Text("F1")
                    .font(.caption.weight(.black))
                    .tracking(0.5)
                    .foregroundStyle(F1Theme.accent)
            }
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

    private var selectedOutcome: MobileOutcome {
        fixture.outcomes.first { $0.id == selectedOutcomeID } ?? fixture.mostLikelyOutcome
    }

    var body: some View {
        ZStack {
            F1Background()
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 18) {
                    BrandHeader(
                        eyebrow: "Football 1",
                        title: "Match intelligence",
                        subtitle: "Result first. Price second. Stake last."
                    )
                    .padding(.top, 8)

                    DataStatePill(isProspective: fixture.isProspective, message: loadMessage)
                    FixtureRail(fixtures: fixtures, selectedFixtureID: $selectedFixtureID)
                    MatchCallHero(fixture: fixture)
                    PriceDecisionCard(fixture: fixture)
                    OutcomeProbabilityCard(fixture: fixture)
                    OutcomeSelector(fixture: fixture, selectedOutcomeID: $selectedOutcomeID)
                    OutcomeDeepDiveCard(fixture: fixture, outcome: selectedOutcome)
                    FoundingPrincipleStrip()
                    Spacer(minLength: 24)
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
            }
        }
        .animation(.easeInOut(duration: 0.28), value: fixture.id)
    }
}

private struct DataStatePill: View {
    let isProspective: Bool
    let message: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 7) {
                Circle()
                    .fill(isProspective ? F1Theme.positive : F1Theme.caution)
                    .frame(width: 7, height: 7)
                    .shadow(color: (isProspective ? F1Theme.positive : F1Theme.caution).opacity(0.55), radius: 5)
                Text(isProspective ? "REAL DATA · LOCKED BEFORE KICKOFF" : "INTERFACE PREVIEW")
                    .font(.caption2.weight(.bold))
                    .tracking(0.8)
                    .foregroundStyle(isProspective ? F1Theme.positive : F1Theme.caution)
            }
            if let message {
                Text(message)
                    .font(.caption)
                    .foregroundStyle(F1Theme.secondary)
            }
        }
    }
}

private struct FixtureRail: View {
    let fixtures: [MobileFixture]
    @Binding var selectedFixtureID: String

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(fixtures) { fixture in
                    let selected = selectedFixtureID == fixture.id
                    Button {
                        selectedFixtureID = fixture.id
                    } label: {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(fixture.kickoff.uppercased())
                                    .font(.caption2.weight(.bold))
                                    .tracking(0.7)
                                    .lineLimit(1)
                                Spacer(minLength: 8)
                                Circle()
                                    .fill(selected ? F1Theme.accent : F1Theme.tertiary)
                                    .frame(width: 6, height: 6)
                            }
                            .foregroundStyle(selected ? F1Theme.accent : F1Theme.secondary)

                            Text(fixture.home)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(F1Theme.text)
                                .lineLimit(1)
                            Text(fixture.away)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(F1Theme.secondary)
                                .lineLimit(1)

                            HStack(spacing: 5) {
                                Text("CALL")
                                    .foregroundStyle(F1Theme.tertiary)
                                Text(fixture.mostLikelyOutcome.name)
                                    .foregroundStyle(F1Theme.text)
                                Text(fixture.mostLikelyOutcome.football1.f1Percent)
                                    .foregroundStyle(F1Theme.accent)
                                    .monospacedDigit()
                            }
                            .font(.caption2.weight(.bold))
                        }
                        .frame(width: 202, alignment: .leading)
                        .padding(14)
                        .background(
                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .fill(selected ? F1Theme.panelStrong : F1Theme.panel)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .stroke(selected ? F1Theme.accent.opacity(0.50) : F1Theme.stroke, lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private struct MatchCallHero: View {
    let fixture: MobileFixture

    private var call: MobileOutcome { fixture.mostLikelyOutcome }

    private var shapeLabel: String {
        if call.football1 >= 0.70 { return "CLEAR FAVOURITE" }
        if call.football1 >= 0.55 { return "FAVOURITE" }
        if call.football1 >= 0.45 { return "LEAN" }
        return "OPEN MATCH"
    }

    private var plainCall: String {
        call.id == "D"
            ? "Football 1 makes the draw the single most likely result."
            : "Football 1 makes \(call.name) the most likely winner."
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(fixture.kickoff.uppercased())
                        .font(.caption2.weight(.bold))
                        .tracking(1.2)
                        .foregroundStyle(F1Theme.secondary)
                    Text("\(fixture.home)  ·  \(fixture.away)")
                        .font(.headline)
                        .foregroundStyle(F1Theme.text)
                }
                Spacer()
                Text(shapeLabel)
                    .font(.caption2.weight(.bold))
                    .tracking(0.8)
                    .foregroundStyle(F1Theme.accent)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(Capsule().fill(F1Theme.accent.opacity(0.11)))
            }

            VStack(alignment: .leading, spacing: 2) {
                Text("OUR CALL")
                    .font(.caption2.weight(.bold))
                    .tracking(1.7)
                    .foregroundStyle(F1Theme.secondary)
                Text(call.name.uppercased())
                    .font(.system(size: 42, weight: .black, design: .rounded))
                    .foregroundStyle(F1Theme.text)
                    .lineLimit(1)
                    .minimumScaleFactor(0.68)
                Text(call.football1.f1Percent)
                    .font(.system(size: 60, weight: .light, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(F1Theme.accent)
                    .contentTransition(.numericText())
            }

            Text(plainCall)
                .font(.title3.weight(.semibold))
                .foregroundStyle(F1Theme.text.opacity(0.90))

            ProbabilityTriplet(fixture: fixture, emphasizedID: call.id)

            HStack(spacing: 6) {
                Image(systemName: fixture.isProspective ? "lock.fill" : "testtube.2")
                Text(fixture.isProspective
                     ? "\(fixture.bookmakerCount) bookmaker prices · forecast locked before kickoff"
                     : "\(fixture.bookmakerCount) bookmaker prices · preview data")
            }
            .font(.caption)
            .foregroundStyle(F1Theme.secondary)
        }
        .padding(20)
        .background(
            ZStack {
                RoundedRectangle(cornerRadius: 30, style: .continuous)
                    .fill(F1Theme.panelStrong)
                LinearGradient(
                    colors: [F1Theme.accent.opacity(0.15), Color.clear],
                    startPoint: .topTrailing,
                    endPoint: .bottomLeading
                )
                .clipShape(RoundedRectangle(cornerRadius: 30, style: .continuous))
            }
        )
        .overlay(
            RoundedRectangle(cornerRadius: 30, style: .continuous)
                .stroke(F1Theme.accent.opacity(0.22), lineWidth: 1)
        )
    }
}

private struct ProbabilityTriplet: View {
    let fixture: MobileFixture
    let emphasizedID: String

    var body: some View {
        HStack(spacing: 8) {
            ForEach(fixture.outcomes) { outcome in
                VStack(alignment: .leading, spacing: 4) {
                    Text(outcome.id == "H" ? "HOME" : (outcome.id == "D" ? "DRAW" : "AWAY"))
                        .font(.caption2.weight(.bold))
                        .tracking(0.8)
                        .foregroundStyle(F1Theme.tertiary)
                    Text(outcome.football1.f1Percent)
                        .font(.headline.monospacedDigit())
                        .foregroundStyle(outcome.id == emphasizedID ? F1Theme.accent : F1Theme.text)
                    Text(outcome.name)
                        .font(.caption2)
                        .foregroundStyle(F1Theme.secondary)
                        .lineLimit(1)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(outcome.id == emphasizedID ? F1Theme.accent.opacity(0.09) : Color.white.opacity(0.035))
                )
            }
        }
    }
}

private struct PriceDecisionCard: View {
    let fixture: MobileFixture

    private var call: MobileOutcome { fixture.mostLikelyOutcome }
    private var bestPrice: MobileOutcome { fixture.bestPriceOutcome }

    private var verdict: String {
        call.ev > 0 ? "PRICE INTEREST" : "PASS"
    }

    private var verdictColor: Color {
        call.ev > 0 ? F1Theme.positive : F1Theme.caution
    }

    private var headline: String {
        if call.ev > 0 {
            return "Likely winner. Price above our fair line."
        }
        return "Likely winner. Wrong price."
    }

    private var explanation: String {
        if call.ev > 0 {
            return "\(call.name) is Football 1's result call and the quoted odds of \(call.odds.f1Odds) are above our fair odds of \(call.fairOdds.f1Odds). This is research interest, not a validated staking instruction."
        }
        return "\(call.name) is still Football 1's result call, but odds of \(call.odds.f1Odds) are below our fair odds of \(call.fairOdds.f1Odds). We would not buy the likely winner at this price."
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 15) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("PRICE")
                        .font(.caption2.weight(.bold))
                        .tracking(1.6)
                        .foregroundStyle(F1Theme.secondary)
                    Text(verdict)
                        .font(.system(size: 25, weight: .black, design: .rounded))
                        .foregroundStyle(verdictColor)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("QUOTED")
                        .font(.caption2.bold())
                        .foregroundStyle(F1Theme.tertiary)
                    Text(call.odds.f1Odds)
                        .font(.title2.monospacedDigit().weight(.bold))
                    Text("FAIR \(call.fairOdds.f1Odds)")
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(F1Theme.secondary)
                }
            }

            Text(headline)
                .font(.title3.weight(.bold))
                .foregroundStyle(F1Theme.text)
            Text(explanation)
                .font(.subheadline)
                .foregroundStyle(F1Theme.secondary)

            if bestPrice.id != call.id && bestPrice.ev > 0 {
                Divider().overlay(F1Theme.stroke)
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: "arrow.triangle.branch")
                        .foregroundStyle(F1Theme.accent)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("BEST PRICE DISCREPANCY")
                            .font(.caption2.bold())
                            .tracking(0.9)
                            .foregroundStyle(F1Theme.accent)
                        Text("\(call.name) is more likely. \(bestPrice.name) is the more interesting price.")
                            .font(.subheadline.weight(.semibold))
                        Text("Model-implied return at the quoted price: \(bestPrice.ev.f1SignedPercent). No threshold has earned promotion.")
                            .font(.caption)
                            .foregroundStyle(F1Theme.secondary)
                    }
                }
            }

            HStack {
                Text("STAKE")
                    .font(.caption2.bold())
                    .tracking(1.0)
                    .foregroundStyle(F1Theme.tertiary)
                Spacer()
                Text("NO VALIDATED STAKE RULE")
                    .font(.caption2.bold())
                    .foregroundStyle(F1Theme.secondary)
            }
        }
        .f1Card()
    }
}

private struct OutcomeProbabilityCard: View {
    let fixture: MobileFixture

    var body: some View {
        VStack(alignment: .leading, spacing: 13) {
            ModernSectionTitle(kicker: "PROBABILITY", title: "The shape of the match")

            GeometryReader { proxy in
                HStack(spacing: 3) {
                    ForEach(fixture.outcomes) { outcome in
                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                            .fill(outcome.id == fixture.mostLikelyOutcome.id ? F1Theme.accent : Color.white.opacity(0.15))
                            .frame(width: max(2, proxy.size.width * outcome.football1 - 2))
                    }
                }
            }
            .frame(height: 12)

            ProbabilityTriplet(fixture: fixture, emphasizedID: fixture.mostLikelyOutcome.id)
        }
        .f1Card()
    }
}

private struct OutcomeSelector: View {
    let fixture: MobileFixture
    @Binding var selectedOutcomeID: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ModernSectionTitle(kicker: "INSPECT", title: "Choose an outcome")
            HStack(spacing: 8) {
                ForEach(fixture.outcomes) { outcome in
                    let selected = selectedOutcomeID == outcome.id
                    Button {
                        selectedOutcomeID = outcome.id
                    } label: {
                        VStack(spacing: 5) {
                            Text(outcome.name)
                                .font(.caption.weight(.semibold))
                                .lineLimit(1)
                            Text(outcome.football1.f1Percent)
                                .font(.headline.monospacedDigit())
                        }
                        .foregroundStyle(selected ? F1Theme.background : F1Theme.text)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 11)
                        .background(
                            RoundedRectangle(cornerRadius: 15, style: .continuous)
                                .fill(selected ? F1Theme.accent : F1Theme.panel)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private struct OutcomeDeepDiveCard: View {
    let fixture: MobileFixture
    let outcome: MobileOutcome
    @State private var showTechnical = false

    private var priceDescription: String {
        outcome.ev >= 0
            ? "The quoted price is above Football 1's fair price."
            : "The quoted price is below Football 1's fair price."
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 15) {
            HStack {
                ModernSectionTitle(kicker: "DETAIL", title: outcome.name)
                Spacer()
                Text(outcome.ev.f1SignedPercent)
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(outcome.ev >= 0 ? F1Theme.positive : F1Theme.negative)
            }

            HStack(spacing: 8) {
                MetricTile(label: "F1", value: outcome.football1.f1Percent)
                MetricTile(label: "MARKET", value: outcome.market.f1Percent)
                MetricTile(label: "ODDS", value: outcome.odds.f1Odds)
                MetricTile(label: "FAIR", value: outcome.fairOdds.f1Odds)
            }

            Text(priceDescription)
                .font(.subheadline.weight(.semibold))
            Text("At odds of \(outcome.odds.f1Odds), \(outcome.name) needs to happen \(outcome.breakEven.f1Percent) of the time to break even. Football 1 estimates \(outcome.football1.f1Percent).")
                .font(.subheadline)
                .foregroundStyle(F1Theme.secondary)

            DisclosureGroup("Technical evidence", isExpanded: $showTechnical) {
                VStack(alignment: .leading, spacing: 7) {
                    PriceLine(label: "Football 1 minus market", value: outcome.edge.f1SignedPercent)
                    PriceLine(label: "Model-implied return", value: outcome.ev.f1SignedPercent)
                    if outcome.elo.isFinite {
                        PriceLine(label: "Elo context", value: outcome.elo.f1Percent)
                    }
                    if outcome.poisson.isFinite {
                        PriceLine(label: "Poisson context", value: outcome.poisson.f1Percent)
                    }
                    if !outcome.elo.isFinite || !outcome.poisson.isFinite {
                        Text("Fixture-level shadow-model context is not present in this locked live snapshot. It is not reconstructed in Swift.")
                            .font(.caption)
                            .foregroundStyle(F1Theme.secondary)
                    }
                    if fixture.isProspective {
                        Text("This probability was locked before kickoff. No positive-EV threshold has yet earned prospective promotion.")
                            .font(.caption)
                            .foregroundStyle(F1Theme.secondary)
                    }
                }
                .padding(.top, 8)
            }
            .font(.caption.weight(.semibold))
            .tint(F1Theme.accent)
        }
        .f1Card()
    }
}

private struct MetricTile: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption2.bold())
                .tracking(0.7)
                .foregroundStyle(F1Theme.tertiary)
            Text(value)
                .font(.subheadline.monospacedDigit().weight(.bold))
                .foregroundStyle(F1Theme.text)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 13).fill(Color.white.opacity(0.035)))
    }
}

private struct PriceLine: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .foregroundStyle(F1Theme.secondary)
            Spacer(minLength: 12)
            Text(value)
                .monospacedDigit()
                .fontWeight(.semibold)
                .foregroundStyle(F1Theme.text)
        }
        .font(.subheadline)
    }
}

private struct FoundingPrincipleStrip: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("FOOTBALL 1")
                .font(.caption2.bold())
                .tracking(1.4)
                .foregroundStyle(F1Theme.accent)
            Text("Winning is an outcome. Making money is a relationship between probability and price.")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(F1Theme.secondary)
        }
        .padding(.vertical, 6)
    }
}

private struct ModernSectionTitle: View {
    let kicker: String
    let title: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(kicker)
                .font(.caption2.bold())
                .tracking(1.3)
                .foregroundStyle(F1Theme.accent)
            Text(title)
                .font(.headline)
                .foregroundStyle(F1Theme.text)
        }
    }
}

private struct RealityView: View {
    let fixtures: [MobileFixture]
    @Binding var selectedFixtureID: String

    private var fixture: MobileFixture {
        fixtures.first { $0.id == selectedFixtureID } ?? fixtures[0]
    }

    var body: some View {
        ZStack {
            F1Background()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    BrandHeader(
                        eyebrow: "Eyes wide open",
                        title: "Result ≠ bet",
                        subtitle: "The app keeps prediction, price and stake separate."
                    )
                    .padding(.top, 8)

                    FixtureRail(fixtures: fixtures, selectedFixtureID: $selectedFixtureID)
                    DecisionLayerCard(
                        number: "01",
                        kicker: "RESULT",
                        title: fixture.mostLikelyOutcome.name.uppercased(),
                        metric: fixture.mostLikelyOutcome.football1.f1Percent,
                        detail: fixture.mostLikelyOutcome.id == "D"
                            ? "The draw is Football 1's single most likely result."
                            : "\(fixture.mostLikelyOutcome.name) are Football 1's most likely winner."
                    )
                    DecisionLayerCard(
                        number: "02",
                        kicker: "PRICE",
                        title: fixture.mostLikelyOutcome.ev > 0 ? "ABOVE OUR FAIR LINE" : "PASS",
                        metric: fixture.mostLikelyOutcome.odds.f1Odds,
                        detail: priceRealityText(for: fixture)
                    )
                    DecisionLayerCard(
                        number: "03",
                        kicker: "STAKE",
                        title: "NO VALIDATED RULE",
                        metric: "—",
                        detail: "Football 1 can identify a likely result and a price discrepancy without pretending that a staking threshold has already earned the right to act."
                    )
                    BestTransactionCard(fixture: fixture)
                    RealityPrinciplesCard()
                    Spacer(minLength: 24)
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
            }
        }
        .animation(.easeInOut(duration: 0.28), value: fixture.id)
    }

    private func priceRealityText(for fixture: MobileFixture) -> String {
        let call = fixture.mostLikelyOutcome
        if call.ev > 0 {
            return "The current odds on \(call.name) are above Football 1's fair odds. That is a price observation, not a bet instruction."
        }
        return "\(call.name) remain the result call, but the quoted odds are too short on Football 1's current estimate."
    }
}

private struct DecisionLayerCard: View {
    let number: String
    let kicker: String
    let title: String
    let metric: String
    let detail: String

    var body: some View {
        HStack(alignment: .top, spacing: 15) {
            Text(number)
                .font(.caption.monospacedDigit().weight(.bold))
                .foregroundStyle(F1Theme.tertiary)
                .frame(width: 24, alignment: .leading)
            VStack(alignment: .leading, spacing: 7) {
                Text(kicker)
                    .font(.caption2.bold())
                    .tracking(1.5)
                    .foregroundStyle(F1Theme.accent)
                HStack(alignment: .firstTextBaseline) {
                    Text(title)
                        .font(.title3.weight(.black))
                        .foregroundStyle(F1Theme.text)
                    Spacer()
                    Text(metric)
                        .font(.title2.monospacedDigit().weight(.light))
                        .foregroundStyle(F1Theme.accent)
                }
                Text(detail)
                    .font(.subheadline)
                    .foregroundStyle(F1Theme.secondary)
            }
        }
        .f1Card()
    }
}

private struct BestTransactionCard: View {
    let fixture: MobileFixture

    private var call: MobileOutcome { fixture.mostLikelyOutcome }
    private var best: MobileOutcome { fixture.bestPriceOutcome }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ModernSectionTitle(kicker: "IMPORTANT", title: "Most likely ≠ best transaction")
            if best.id == call.id {
                Text("This match currently points to the same outcome for both result probability and the largest model/price discrepancy: \(call.name).")
                    .font(.subheadline)
                    .foregroundStyle(F1Theme.secondary)
            } else {
                Text("Football 1 predicts \(call.name) as the most likely result. The largest model/price discrepancy is \(best.name) at \(best.odds.f1Odds).")
                    .font(.subheadline)
                    .foregroundStyle(F1Theme.secondary)
            }
            Text("Price discrepancy: \(best.ev.f1SignedPercent) model-implied return · research only")
                .font(.caption.monospacedDigit().weight(.semibold))
                .foregroundStyle(best.ev > 0 ? F1Theme.positive : F1Theme.secondary)
        }
        .f1Card()
    }
}

private struct RealityPrinciplesCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 13) {
            ModernSectionTitle(kicker: "DISCIPLINE", title: "Judge the decision at kickoff")
            PrincipleRow(title: "A likely winner can be a bad price", detail: "Probability answers what may happen. Price answers what you are being asked to pay for that probability.")
            PrincipleRow(title: "A winner can be deliberately passed", detail: "A result does not retrospectively make an unattractive price attractive.")
            PrincipleRow(title: "Interesting evidence is not automatic weight", detail: "Shadow models keep auditioning. They do not move the official probability unless they prove they improve unseen forecasts.")
        }
        .f1Card()
    }
}

private struct PrincipleRow: View {
    let title: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.subheadline.weight(.semibold))
            Text(detail)
                .font(.caption)
                .foregroundStyle(F1Theme.secondary)
        }
    }
}

private struct ModelModule: Identifiable {
    let id = UUID()
    let name: String
    let description: String
    let status: String
    let note: String
}

private struct ModelStatusView: View {
    private let modules: [ModelModule] = [
        ModelModule(
            name: "Market",
            description: "Bookmaker prices converted into probabilities after removing the built-in margin.",
            status: "STARTING POINT",
            note: "Baseline and reference. Not assumed truth."
        ),
        ModelModule(
            name: "Football 1",
            description: "A deliberately small market-anchored adjustment being tracked prospectively.",
            status: "TESTING",
            note: "Has not earned validated betting-signal status."
        ),
        ModelModule(
            name: "Elo",
            description: "A running measure of team strength based on results.",
            status: "CONTEXT",
            note: "Historically useful context; zero permission to move the live probability."
        ),
        ModelModule(
            name: "Dynamic Bayesian strength",
            description: "Tracks changing team strength with explicit uncertainty and time evolution.",
            status: "CONTEXT",
            note: "Historically did not improve the market-anchored stack. It remains a shadow model."
        ),
        ModelModule(
            name: "Regime / surprise",
            description: "Watches for teams repeatedly outperforming or underperforming Bayesian expectation.",
            status: "CONTEXT",
            note: "Interesting research signal. No live decision weight."
        ),
        ModelModule(
            name: "Poisson",
            description: "Models likely scorelines and the shape of the draw probability.",
            status: "CONTEXT",
            note: "Useful score context; did not earn incremental live weight."
        ),
        ModelModule(
            name: "Dixon–Coles",
            description: "A football-specific attack/defence score model with low-score dependence.",
            status: "CONTEXT",
            note: "Properly audited and still zero-weight after historical OOS testing."
        ),
        ModelModule(
            name: "Home / Away",
            description: "Checks whether venue-specific behaviour adds information beyond the market.",
            status: "CONTEXT",
            note: "Auditioning only."
        ),
        ModelModule(
            name: "Head-to-head",
            description: "Past meetings between the same two clubs.",
            status: "NO WEIGHT",
            note: "Shown for transparency; explicitly excluded from the final probability."
        )
    ]

    var body: some View {
        ZStack {
            F1Background()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    BrandHeader(
                        eyebrow: "Model room",
                        title: "Always auditioning",
                        subtitle: "Interesting information is not the same thing as information allowed to change the probability."
                    )
                    .padding(.top, 8)

                    PermissionCard()

                    ForEach(modules) { module in
                        ModelModuleCard(module: module)
                    }

                    StatusGlossaryCard()
                    Spacer(minLength: 24)
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
            }
        }
    }
}

private struct PermissionCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("PERMISSION TO MOVE")
                .font(.caption2.bold())
                .tracking(1.5)
                .foregroundStyle(F1Theme.accent)
            Text("Evidence is cheap. Weight is earned.")
                .font(.title2.weight(.bold))
            Text("Every model may produce an opinion. Only models that improve genuinely unseen probabilities are allowed to alter Football 1's final live estimate.")
                .font(.subheadline)
                .foregroundStyle(F1Theme.secondary)
        }
        .f1Card(strong: true)
    }
}

private struct ModelModuleCard: View {
    let module: ModelModule

    private var statusColor: Color {
        switch module.status {
        case "STARTING POINT": return F1Theme.accent
        case "TESTING": return F1Theme.caution
        case "NO WEIGHT": return F1Theme.negative
        default: return F1Theme.secondary
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .firstTextBaseline) {
                Text(module.name)
                    .font(.headline)
                    .foregroundStyle(F1Theme.text)
                Spacer()
                Text(module.status)
                    .font(.caption2.bold())
                    .tracking(0.7)
                    .foregroundStyle(statusColor)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 5)
                    .background(Capsule().fill(statusColor.opacity(0.10)))
            }
            Text(module.description)
                .font(.subheadline)
                .foregroundStyle(F1Theme.secondary)
            Text(module.note)
                .font(.caption)
                .foregroundStyle(F1Theme.tertiary)
        }
        .f1Card()
    }
}

private struct StatusGlossaryCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ModernSectionTitle(kicker: "STATUS", title: "What the labels mean")
            GlossaryLine(term: "STARTING POINT", detail: "The market baseline after bookmaker margin removal.")
            GlossaryLine(term: "TESTING", detail: "Prospective candidate. Not a validated betting signal.")
            GlossaryLine(term: "CONTEXT", detail: "Research evidence with zero permission to move the final probability.")
            GlossaryLine(term: "NO WEIGHT", detail: "Deliberately excluded from the live calculation.")
        }
        .f1Card()
    }
}

private struct GlossaryLine: View {
    let term: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(term)
                .font(.caption2.bold())
                .tracking(0.7)
                .foregroundStyle(F1Theme.accent)
            Text(detail)
                .font(.caption)
                .foregroundStyle(F1Theme.secondary)
        }
    }
}

private extension View {
    func f1Card(strong: Bool = false) -> some View {
        self
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(17)
            .background(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(strong ? F1Theme.panelStrong : F1Theme.panel)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .stroke(F1Theme.stroke, lineWidth: 1)
            )
    }
}
