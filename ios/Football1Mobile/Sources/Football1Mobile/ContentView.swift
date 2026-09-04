import SwiftUI

struct ContentView: View {
    @State private var selectedFixture = MobilePreviewData.fixtures[0]
    @State private var selectedOutcomeID = "H"

    var body: some View {
        TabView {
            NavigationStack {
                LiveMobileView(
                    selectedFixture: $selectedFixture,
                    selectedOutcomeID: $selectedOutcomeID
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
                ResearchMobileView()
                    .navigationTitle("Research")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem { Label("Research", systemImage: "chart.line.uptrend.xyaxis") }
        }
        .tint(.blue)
    }
}

private struct LiveMobileView: View {
    @Binding var selectedFixture: MobileFixture
    @Binding var selectedOutcomeID: String

    private var selectedOutcome: MobileOutcome {
        selectedFixture.outcomes.first { $0.id == selectedOutcomeID } ?? selectedFixture.strongestOutcome
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                PrincipleCard()
                PreviewPill()
                fixtureStrip
                MatchHeader(fixture: selectedFixture)
                DecisionRealityCard(outcome: selectedOutcome)
                OutcomeSelector(
                    fixture: selectedFixture,
                    selectedOutcomeID: $selectedOutcomeID
                )
                ModelRoomCard(outcome: selectedOutcome)
                PriceRealityCard(outcome: selectedOutcome)
                ExplanationCard(fixture: selectedFixture, outcome: selectedOutcome)
                Spacer(minLength: 24)
            }
            .padding(16)
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .onChange(of: selectedFixture.id) { _, _ in
            selectedOutcomeID = selectedFixture.strongestOutcome.id
        }
    }

    private var fixtureStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(MobilePreviewData.fixtures) { fixture in
                    Button {
                        selectedFixture = fixture
                    } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(fixture.home)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.primary)
                            Text(fixture.away)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            HStack {
                                Text(fixture.kickoff)
                                Spacer(minLength: 6)
                                Text(fixture.strongestOutcome.ev.f1SignedPercent)
                                    .foregroundStyle(fixture.strongestOutcome.ev >= 0 ? .green : .red)
                            }
                            .font(.caption2.weight(.semibold))
                        }
                        .frame(width: 188, alignment: .leading)
                        .padding(12)
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .fill(selectedFixture.id == fixture.id ? Color.blue.opacity(0.12) : Color(uiColor: .secondarySystemGroupedBackground))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 14)
                                .stroke(selectedFixture.id == fixture.id ? Color.blue.opacity(0.55) : Color.secondary.opacity(0.16), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                }
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

private struct PreviewPill: View {
    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: "testtube.2")
            Text("INTERFACE PREVIEW · MODEL VALUES NOT YET PROSPECTIVE")
        }
        .font(.caption2.weight(.bold))
        .foregroundStyle(.orange)
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(Capsule().fill(Color.orange.opacity(0.12)))
    }
}

private struct MatchHeader: View {
    let fixture: MobileFixture

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(fixture.kickoff.uppercased())
                .font(.caption2.weight(.bold))
                .tracking(1)
                .foregroundStyle(.secondary)
            Text("\(fixture.home) vs \(fixture.away)")
                .font(.title2.bold())
            Text("\(fixture.bookmakerCount) complete UK books · preview model layer")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

private struct DecisionRealityCard: View {
    let outcome: MobileOutcome

    private var decision: (label: String, color: Color, title: String, detail: String) {
        if outcome.ev < -0.02 {
            return (
                "PASS",
                .red,
                "Prediction and price do not agree",
                "The offered price requires \(outcome.breakEven.f1Percent) to break even, above Football 1's \(outcome.football1.f1Percent) preview estimate."
            )
        }
        if outcome.ev >= 0.05 {
            return (
                "CANDIDATE",
                .green,
                "The price deserves inspection",
                "The price compensates more generously than the Football 1 preview probability implies. That is not a claim of certainty."
            )
        }
        return (
            "CAUTION",
            .orange,
            "The margin is thin",
            "Football 1 and the market are close. There is little room for estimation error."
        )
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Text("EYES WIDE OPEN")
                    .font(.caption2.weight(.bold))
                    .tracking(1)
                    .foregroundStyle(.secondary)
                Text(decision.title)
                    .font(.headline)
                Text(decision.detail)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Text(decision.label)
                .font(.caption.weight(.heavy))
                .foregroundStyle(decision.color)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(Capsule().fill(decision.color.opacity(0.12)))
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct OutcomeSelector: View {
    let fixture: MobileFixture
    @Binding var selectedOutcomeID: String

    var body: some View {
        VStack(spacing: 10) {
            ForEach(fixture.outcomes) { outcome in
                Button {
                    selectedOutcomeID = outcome.id
                } label: {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(outcome.name)
                                .font(.headline)
                                .foregroundStyle(.primary)
                            Text("Football 1 \(outcome.football1.f1Percent) · Market \(outcome.market.f1Percent)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 3) {
                            Text(outcome.odds.f1Odds)
                                .font(.headline.monospacedDigit())
                                .foregroundStyle(.primary)
                            Text("EV \(outcome.ev.f1SignedPercent)")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(outcome.ev >= 0 ? .green : .red)
                        }
                    }
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: 15)
                            .fill(selectedOutcomeID == outcome.id ? Color.blue.opacity(0.10) : Color(uiColor: .secondarySystemGroupedBackground))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 15)
                            .stroke(selectedOutcomeID == outcome.id ? Color.blue.opacity(0.55) : Color.secondary.opacity(0.14), lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }
}

private struct ModelRoomCard: View {
    let outcome: MobileOutcome

    private var rows: [(String, Double)] {
        [
            ("Market", outcome.market),
            ("Elo", outcome.elo),
            ("Poisson", outcome.poisson),
            ("Football 1", outcome.football1)
        ]
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
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct PriceRealityCard: View {
    let outcome: MobileOutcome

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Price reality", systemImage: "scalemass")
                .font(.headline)
            PriceLine(label: "Available price", value: outcome.odds.f1Odds)
            PriceLine(label: "Break-even probability", value: outcome.breakEven.f1Percent)
            PriceLine(label: "Football 1 probability", value: outcome.football1.f1Percent)
            PriceLine(label: "Model vs market", value: outcome.edge.f1SignedPercent)
            PriceLine(label: "Model-implied EV", value: outcome.ev.f1SignedPercent, emphasized: true, positive: outcome.ev >= 0)
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct PriceLine: View {
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
                .foregroundStyle(emphasized ? (positive ? Color.green : Color.red) : Color.primary)
        }
        .font(.subheadline)
    }
}

private struct ExplanationCard: View {
    let fixture: MobileFixture
    let outcome: MobileOutcome

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text("WHY FOOTBALL 1 SAYS THIS")
                .font(.caption2.weight(.bold))
                .tracking(1)
                .foregroundStyle(.secondary)
            Text("Football 1 currently puts \(outcome.name) at \(outcome.football1.f1Percent) in this interface preview. At odds of \(outcome.odds.f1Odds), the position needs \(outcome.breakEven.f1Percent) to break even. The result may still win or lose; the decision question is whether the price compensates for that uncertainty.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
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
                LessonCard(kicker: "87% LIKELY WINNER", title: "BAD PRICE — PASS", detail: "A high-probability outcome can still be a poor transaction when the price demands an even higher break-even probability.", color: .red)
                LessonCard(kicker: "18% CHANCE OF WINNING", title: "PRICE MAY BE ATTRACTIVE", detail: "A low-probability outcome can still be rational if the odds compensate for frequent losses.", color: .green)
                LessonCard(kicker: "RESULT ≠ PROCESS", title: "Judge the decision at kickoff", detail: "A good bet can lose. A bad bet can win. The ledger keeps the pre-match decision separate from the final result.", color: .blue)
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
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(kicker).font(.caption2.bold()).tracking(1).foregroundStyle(.secondary)
            Text(title).font(.title3.bold()).foregroundStyle(color)
            Text(detail).font(.subheadline).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }
}

private struct ModelStatusView: View {
    private let modules = [
        ("Elo", "Underlying team strength", "CONTEXT", Color.blue),
        ("Poisson", "Score distribution / draw shape", "CONTEXT", Color.blue),
        ("Home / Away", "Venue-role behaviour", "CONTEXT", Color.blue),
        ("Head-to-head", "Pair-specific history", "NO WEIGHT", Color.red),
        ("Market", "Collective information + price", "ANCHOR", Color.green),
        ("Football 1 tightener", "Conservative residual adjustment", "TESTING", Color.orange)
    ]

    var body: some View {
        List {
            Section {
                Text("Every model gets an opinion. Not every model earns weight.")
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
                            .foregroundStyle(item.3)
                    }
                    .padding(.vertical, 3)
                }
            }
        }
    }
}

private struct ResearchMobileView: View {
    var body: some View {
        List {
            Section("Frozen OOS results") {
                ResearchRow(title: "Market log loss", value: "0.960279", detail: "Bet365 de-vigged baseline")
                ResearchRow(title: "Elo top-pick accuracy", value: "53.45%", detail: "2,245 / 4,200 correct")
                ResearchRow(title: "Blind Elo betting ROI", value: "−4.16%", detail: "Being right did not make the price good")
                ResearchRow(title: "Residual slant log loss", value: "0.962730", detail: "Still worse than the market")
            }
            Section("Prospective principle") {
                Text("Predictions are frozen before kickoff. Results settle later. No threshold is promoted after inspecting the outcome.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private struct ResearchRow: View {
    let title: String
    let value: String
    let detail: String

    var body: some View {
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
