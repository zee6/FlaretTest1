import Charts
import SwiftUI

struct EloResearchDashboard: View {
    let fixtures: [MobileFixture]
    let selectedFixtureID: String

    @State private var document: EloResearchDocument?
    @State private var loadError: String?
    @State private var comparisonFixtureID: String = ""
    @State private var horizon: EloHorizon = .season
    @State private var showTechnical = false

    private var comparisonFixture: MobileFixture? {
        let preferred = comparisonFixtureID.isEmpty ? selectedFixtureID : comparisonFixtureID
        return fixtures.first { $0.id == preferred } ?? fixtures.first
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                researchSummary
                frozenEvidence

                if let document {
                    eloComparison(document)
                    eloTable(document)
                    methodology(document)
                } else if let loadError {
                    unavailableCard(loadError)
                } else {
                    ProgressView("Loading Elo research…")
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 30)
                }
            }
            .padding(16)
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .task {
            if comparisonFixtureID.isEmpty {
                comparisonFixtureID = selectedFixtureID
            }
            await loadEloResearch()
        }
        .onChange(of: selectedFixtureID) { _, newValue in
            comparisonFixtureID = newValue
        }
    }

    private var researchSummary: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text("SHOW ME THE EVIDENCE")
                .font(.caption2.bold())
                .tracking(1)
                .foregroundStyle(.secondary)
            Text("Research keeps the technical evidence behind the simple match screen.")
                .font(.title3.bold())
            Text("Elo is useful for seeing how team strength has moved through time. It is context only: our historical test did not show that Elo improves the market probability.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }

    private var frozenEvidence: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Historical test on unseen matches")
                .font(.headline)
            EvidenceRow(label: "Market log loss", value: "0.960279", note: "Lower is better")
            EvidenceRow(label: "Elo log loss", value: "0.978258", note: "Worse than market")
            EvidenceRow(label: "Elo most-likely result correct", value: "53.45%", note: "2,245 of 4,200")
            EvidenceRow(label: "Blindly backing every Elo pick", value: "−4.16%", note: "Historical ROI")
            Text("The point: being right more often is not the same as being offered a good price.")
                .font(.subheadline.weight(.semibold))
                .padding(.top, 2)
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }

    @ViewBuilder
    private func eloComparison(_ document: EloResearchDocument) -> some View {
        if let fixture = comparisonFixture {
            let home = canonicalTeamName(fixture.home)
            let away = canonicalTeamName(fixture.away)
            let points = chartPoints(document: document, home: home, away: away)

            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Elo through time")
                            .font(.headline)
                        Text("Compare the two clubs in a fixture")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text("CONTEXT")
                        .font(.caption2.bold())
                        .foregroundStyle(.blue)
                }

                Picker("Fixture", selection: $comparisonFixtureID) {
                    ForEach(fixtures) { item in
                        Text("\(item.home) – \(item.away)").tag(item.id)
                    }
                }
                .pickerStyle(.menu)

                Picker("History", selection: $horizon) {
                    ForEach(EloHorizon.allCases) { item in
                        Text(item.rawValue).tag(item)
                    }
                }
                .pickerStyle(.segmented)

                HStack(spacing: 18) {
                    currentRatingLabel(team: home, document: document)
                    currentRatingLabel(team: away, document: document)
                }

                if points.isEmpty {
                    Text("No Elo history is available for this pair in the current research export.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 20)
                } else {
                    Chart(points) { point in
                        LineMark(
                            x: .value("Date", point.date),
                            y: .value("Elo", point.rating)
                        )
                        .foregroundStyle(by: .value("Team", point.team))
                        .interpolationMethod(.linear)
                    }
                    .chartLegend(position: .bottom, alignment: .leading)
                    .chartYAxisLabel("Elo rating")
                    .frame(height: 260)
                }

                Text("The lines show the rating Football 1 had immediately before each EPL match. Gaps can occur when a club was outside the Premier League.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(16)
            .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
        }
    }

    private func eloTable(_ document: EloResearchDocument) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Current EPL Elo table")
                    .font(.headline)
                Spacer()
                Text("5-match change")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            ForEach(document.currentRatings) { row in
                HStack(spacing: 10) {
                    Text("\(row.rank)")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .frame(width: 24, alignment: .trailing)
                    Text(displayTeamName(row.team))
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Text(String(format: "%.0f", row.rating))
                        .font(.subheadline.monospacedDigit().weight(.semibold))
                    Text(signedElo(row.change5Matches))
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(row.change5Matches > 0 ? Color.blue : (row.change5Matches < 0 ? Color.red : Color.secondary))
                        .frame(width: 48, alignment: .trailing)
                }
                .padding(.vertical, 4)
                if row.id != document.currentRatings.last?.id {
                    Divider()
                }
            }

            Text("A higher Elo means stronger recent EPL results under this simple rating system. It is not Football 1's final win probability.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.top, 3)
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }

    private func methodology(_ document: EloResearchDocument) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            DisclosureGroup("Technical detail", isExpanded: $showTechnical) {
                VStack(alignment: .leading, spacing: 7) {
                    Text(document.ratingPolicy)
                    Text(document.historyPolicy)
                    Text("Base rating: \(document.parameters.baseRating, specifier: "%.0f") · K factor: \(document.parameters.kFactor, specifier: "%.0f") · home advantage: \(document.parameters.homeAdvantage, specifier: "%.0f") Elo points.")
                    Text("Latest research match date: \(document.latestMatchDate). Elo status: context only.")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.top, 8)
            }
            .font(.subheadline.weight(.semibold))
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }

    private func unavailableCard(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Elo research data unavailable")
                .font(.headline)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text("The live probability screen is unaffected.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 18).fill(Color(uiColor: .secondarySystemGroupedBackground)))
    }

    @ViewBuilder
    private func currentRatingLabel(team: String, document: EloResearchDocument) -> some View {
        if let row = document.currentRatings.first(where: { $0.team == team }) {
            VStack(alignment: .leading, spacing: 2) {
                Text(displayTeamName(team))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(String(format: "%.0f Elo", row.rating))
                    .font(.subheadline.monospacedDigit().weight(.semibold))
            }
        }
    }

    private func chartPoints(document: EloResearchDocument, home: String, away: String) -> [EloChartPoint] {
        let latestDate = EloDateParser.date(document.latestMatchDate)
        let cutoff = latestDate.flatMap {
            Calendar.current.date(byAdding: .year, value: -3, to: $0)
        }

        func filtered(team: String) -> [EloChartPoint] {
            (document.histories[team] ?? []).compactMap { point in
                guard let date = EloDateParser.date(point.date) else { return nil }
                switch horizon {
                case .season:
                    guard point.seasonStartYear == document.latestSeasonStartYear else { return nil }
                case .threeYears:
                    if let cutoff, date < cutoff { return nil }
                case .all:
                    break
                }
                return EloChartPoint(team: displayTeamName(team), date: date, rating: point.rating)
            }
        }

        return (filtered(team: home) + filtered(team: away)).sorted { $0.date < $1.date }
    }

    @MainActor
    private func loadEloResearch() async {
        do {
            let (data, response) = try await URLSession.shared.data(from: EloResearchDocument.publicURL)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                throw URLError(.badServerResponse)
            }
            document = try JSONDecoder().decode(EloResearchDocument.self, from: data)
            loadError = nil
        } catch {
            loadError = "Football 1 could not read the public Elo research export."
        }
    }
}

private struct EvidenceRow: View {
    let label: String
    let value: String
    let note: String

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.subheadline)
                Text(note)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 12)
            Text(value)
                .font(.subheadline.monospacedDigit().weight(.bold))
        }
    }
}

private enum EloHorizon: String, CaseIterable, Identifiable {
    case season = "Season"
    case threeYears = "3 years"
    case all = "All"

    var id: String { rawValue }
}

private struct EloChartPoint: Identifiable {
    let team: String
    let date: Date
    let rating: Double

    var id: String { "\(team)-\(date.timeIntervalSince1970)-\(rating)" }
}

private struct EloResearchDocument: Decodable {
    let schemaVersion: Int
    let model: String
    let latestSeasonStartYear: Int
    let latestMatchDate: String
    let parameters: EloParameters
    let ratingPolicy: String
    let historyPolicy: String
    let productStatus: String
    let currentRatings: [EloRatingRow]
    let histories: [String: [EloHistoryPoint]]

    static let publicURL = URL(string: "https://raw.githubusercontent.com/zee6/FlaretTest1/master/research/elo_research.json")!

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case model
        case latestSeasonStartYear = "latest_season_start_year"
        case latestMatchDate = "latest_match_date"
        case parameters
        case ratingPolicy = "rating_policy"
        case historyPolicy = "history_policy"
        case productStatus = "product_status"
        case currentRatings = "current_ratings"
        case histories
    }
}

private struct EloParameters: Decodable {
    let baseRating: Double
    let scale: Double
    let kFactor: Double
    let homeAdvantage: Double
    let seasonCarry: Double

    enum CodingKeys: String, CodingKey {
        case baseRating = "base_rating"
        case scale
        case kFactor = "k_factor"
        case homeAdvantage = "home_advantage"
        case seasonCarry = "season_carry"
    }
}

private struct EloRatingRow: Decodable, Identifiable {
    let rank: Int
    let team: String
    let rating: Double
    let change5Matches: Double
    let seasonChange: Double

    var id: String { team }

    enum CodingKeys: String, CodingKey {
        case rank
        case team
        case rating
        case change5Matches = "change_5_matches"
        case seasonChange = "season_change"
    }
}

private struct EloHistoryPoint: Decodable {
    let date: String
    let seasonStartYear: Int
    let rating: Double

    enum CodingKeys: String, CodingKey {
        case date
        case seasonStartYear = "season_start_year"
        case rating
    }
}

private enum EloDateParser {
    static func date(_ value: String) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: value)
    }
}

private func canonicalTeamName(_ providerName: String) -> String {
    let map: [String: String] = [
        "AFC Bournemouth": "Bournemouth",
        "Bournemouth": "Bournemouth",
        "Brighton and Hove Albion": "Brighton",
        "Brighton & Hove Albion": "Brighton",
        "Brentford FC": "Brentford",
        "Coventry City": "Coventry",
        "Hull City": "Hull",
        "Ipswich Town": "Ipswich",
        "Leeds United": "Leeds",
        "Manchester City": "Man City",
        "Manchester United": "Man United",
        "Newcastle United": "Newcastle",
        "Nottingham Forest": "Nott'm Forest",
        "Sunderland AFC": "Sunderland",
        "Tottenham Hotspur": "Tottenham"
    ]
    return map[providerName] ?? providerName
}

private func displayTeamName(_ canonicalName: String) -> String {
    let map: [String: String] = [
        "Man City": "Manchester City",
        "Man United": "Manchester United",
        "Nott'm Forest": "Nottingham Forest"
    ]
    return map[canonicalName] ?? canonicalName
}

private func signedElo(_ value: Double) -> String {
    String(format: "%+.0f", value)
}
