import Combine
import Foundation

@MainActor
final class AppModel: ObservableObject {
    @Published var selection: AppSection? = .live
    @Published var selectedFixtureID: String?

    let fixtures: [FixtureRow]
    let ledger: [LedgerRow]
    let researchMetrics: [ResearchMetric]
    let dataHealth: [DataHealthRow]
    let snapshotLabel: String
    let isPreview: Bool

    init() {
        fixtures = PreviewData.fixtures
        ledger = PreviewData.ledger
        researchMetrics = PreviewData.researchMetrics
        dataHealth = PreviewData.dataHealth
        snapshotLabel = "First live API snapshot · 20 fixtures · 1 credit used"
        isPreview = true
        selectedFixtureID = fixtures.first?.id
    }

    var selectedFixture: FixtureRow? {
        guard let selectedFixtureID else { return fixtures.first }
        return fixtures.first { $0.id == selectedFixtureID } ?? fixtures.first
    }

    var rankedMispricing: [(fixture: FixtureRow, quote: OutcomeQuote)] {
        fixtures.compactMap { fixture in
            guard let quote = fixture.strongestQuote else { return nil }
            return (fixture, quote)
        }
        .sorted { $0.quote.predictedEV > $1.quote.predictedEV }
    }
}

private enum PreviewData {
    static func utc(_ year: Int, _ month: Int, _ day: Int, _ hour: Int, _ minute: Int = 0) -> Date {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar.date(from: DateComponents(
            year: year,
            month: month,
            day: day,
            hour: hour,
            minute: minute
        ))!
    }

    static let fixtures: [FixtureRow] = [
        FixtureRow(
            id: "newcastle-bournemouth",
            kickoff: utc(2026, 9, 5, 11, 30),
            homeTeam: "Newcastle United",
            awayTeam: "Bournemouth",
            bookmakerCount: 21,
            status: "Upcoming",
            quotes: [
                OutcomeQuote(outcome: .home, marketProbability: 0.4493, football1Probability: 0.4710, bestOdds: 2.18),
                OutcomeQuote(outcome: .draw, marketProbability: 0.2594, football1Probability: 0.2500, bestOdds: 3.80),
                OutcomeQuote(outcome: .away, marketProbability: 0.2913, football1Probability: 0.2790, bestOdds: 3.50)
            ]
        ),
        FixtureRow(
            id: "brentford-sunderland",
            kickoff: utc(2026, 9, 5, 14),
            homeTeam: "Brentford",
            awayTeam: "Sunderland",
            bookmakerCount: 21,
            status: "Upcoming",
            quotes: [
                OutcomeQuote(outcome: .home, marketProbability: 0.5768, football1Probability: 0.5630, bestOdds: 1.69),
                OutcomeQuote(outcome: .draw, marketProbability: 0.2448, football1Probability: 0.2460, bestOdds: 4.10),
                OutcomeQuote(outcome: .away, marketProbability: 0.1784, football1Probability: 0.1910, bestOdds: 5.90)
            ]
        ),
        FixtureRow(
            id: "brighton-leeds",
            kickoff: utc(2026, 9, 5, 14),
            homeTeam: "Brighton and Hove Albion",
            awayTeam: "Leeds United",
            bookmakerCount: 21,
            status: "Upcoming",
            quotes: [
                OutcomeQuote(outcome: .home, marketProbability: 0.4820, football1Probability: 0.4920, bestOdds: 2.06),
                OutcomeQuote(outcome: .draw, marketProbability: 0.2692, football1Probability: 0.2650, bestOdds: 3.65),
                OutcomeQuote(outcome: .away, marketProbability: 0.2488, football1Probability: 0.2430, bestOdds: 4.00)
            ]
        ),
        FixtureRow(
            id: "forest-tottenham",
            kickoff: utc(2026, 9, 5, 14),
            homeTeam: "Nottingham Forest",
            awayTeam: "Tottenham Hotspur",
            bookmakerCount: 21,
            status: "Upcoming",
            quotes: [
                OutcomeQuote(outcome: .home, marketProbability: 0.3926, football1Probability: 0.3810, bestOdds: 2.52),
                OutcomeQuote(outcome: .draw, marketProbability: 0.2809, football1Probability: 0.2840, bestOdds: 3.55),
                OutcomeQuote(outcome: .away, marketProbability: 0.3265, football1Probability: 0.3350, bestOdds: 3.05)
            ]
        ),
        FixtureRow(
            id: "arsenal-chelsea",
            kickoff: utc(2026, 9, 6, 15, 30),
            homeTeam: "Arsenal",
            awayTeam: "Chelsea",
            bookmakerCount: 20,
            status: "Upcoming",
            quotes: [
                OutcomeQuote(outcome: .home, marketProbability: 0.5622, football1Probability: 0.5510, bestOdds: 1.75),
                OutcomeQuote(outcome: .draw, marketProbability: 0.2473, football1Probability: 0.2510, bestOdds: 4.00),
                OutcomeQuote(outcome: .away, marketProbability: 0.1906, football1Probability: 0.1980, bestOdds: 5.50)
            ]
        )
    ]

    static let ledger: [LedgerRow] = [
        LedgerRow(
            id: "preview-ledger-1",
            timestamp: utc(2026, 9, 4, 9, 12),
            fixture: "Newcastle United — Bournemouth",
            selection: "Home",
            bestOdds: 2.18,
            predictedEV: 0.0268,
            state: "PREVIEW · prospective schema",
            pnl: nil
        ),
        LedgerRow(
            id: "preview-ledger-2",
            timestamp: utc(2026, 9, 4, 9, 12),
            fixture: "Arsenal — Chelsea",
            selection: "Away",
            bestOdds: 5.50,
            predictedEV: 0.0890,
            state: "PREVIEW · prospective schema",
            pnl: nil
        )
    ]

    static let researchMetrics: [ResearchMetric] = [
        ResearchMetric(title: "Market OOS log loss", value: "0.960279", detail: "De-vigged Bet365 pre-closing baseline"),
        ResearchMetric(title: "Football-only log loss", value: "0.979445", detail: "Worse than market by +0.019166"),
        ResearchMetric(title: "Residual slant log loss", value: "0.962730", detail: "Worse than market by +0.002451"),
        ResearchMetric(title: "≥7.5% historical tail", value: "+4.06% ROI", detail: "Observed, not prospectively validated")
    ]

    static let dataHealth: [DataHealthRow] = [
        DataHealthRow(source: "Football-Data EPL", status: "Healthy", detail: "5,340 canonical matches · 2012/13–2026/27"),
        DataHealthRow(source: "The Odds API", status: "Healthy", detail: "20 live/upcoming fixtures · 499 credits remaining after smoke test"),
        DataHealthRow(source: "Prospective ledger", status: "Ready", detail: "Immutable prediction schema merged; first production records pending"),
        DataHealthRow(source: "macOS data bridge", status: "Preview", detail: "Swift shell currently uses preview objects; JSON bridge is next")
    ]
}
