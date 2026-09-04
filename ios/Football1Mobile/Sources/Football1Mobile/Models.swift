import Foundation

struct MobileOutcome: Identifiable, Hashable {
    let id: String
    let name: String
    let market: Double
    let elo: Double
    let poisson: Double
    let football1: Double
    let odds: Double

    var breakEven: Double { 1.0 / odds }
    var ev: Double { football1 * odds - 1.0 }
    var edge: Double { football1 - market }
}

struct MobileFixture: Identifiable, Hashable {
    let id: String
    let kickoff: String
    let home: String
    let away: String
    let bookmakerCount: Int
    let outcomes: [MobileOutcome]

    var strongestOutcome: MobileOutcome {
        outcomes.max { $0.ev < $1.ev } ?? outcomes[0]
    }
}

enum MobilePreviewData {
    static let fixtures: [MobileFixture] = [
        MobileFixture(
            id: "newcastle-bournemouth",
            kickoff: "Sat · 11:30 UTC",
            home: "Newcastle United",
            away: "Bournemouth",
            bookmakerCount: 21,
            outcomes: [
                MobileOutcome(id: "H", name: "Newcastle", market: 0.4493, elo: 0.489, poisson: 0.455, football1: 0.471, odds: 2.18),
                MobileOutcome(id: "D", name: "Draw", market: 0.2594, elo: 0.246, poisson: 0.267, football1: 0.250, odds: 3.80),
                MobileOutcome(id: "A", name: "Bournemouth", market: 0.2913, elo: 0.265, poisson: 0.278, football1: 0.279, odds: 3.50)
            ]
        ),
        MobileFixture(
            id: "brentford-sunderland",
            kickoff: "Sat · 14:00 UTC",
            home: "Brentford",
            away: "Sunderland",
            bookmakerCount: 21,
            outcomes: [
                MobileOutcome(id: "H", name: "Brentford", market: 0.5768, elo: 0.604, poisson: 0.548, football1: 0.563, odds: 1.69),
                MobileOutcome(id: "D", name: "Draw", market: 0.2448, elo: 0.231, poisson: 0.262, football1: 0.246, odds: 4.10),
                MobileOutcome(id: "A", name: "Sunderland", market: 0.1784, elo: 0.165, poisson: 0.190, football1: 0.191, odds: 5.90)
            ]
        ),
        MobileFixture(
            id: "arsenal-chelsea",
            kickoff: "Sun · 15:30 UTC",
            home: "Arsenal",
            away: "Chelsea",
            bookmakerCount: 20,
            outcomes: [
                MobileOutcome(id: "H", name: "Arsenal", market: 0.5622, elo: 0.588, poisson: 0.542, football1: 0.551, odds: 1.75),
                MobileOutcome(id: "D", name: "Draw", market: 0.2473, elo: 0.232, poisson: 0.257, football1: 0.251, odds: 4.00),
                MobileOutcome(id: "A", name: "Chelsea", market: 0.1906, elo: 0.180, poisson: 0.201, football1: 0.198, odds: 5.50)
            ]
        )
    ]
}

extension Double {
    var f1Percent: String { String(format: "%.1f%%", self * 100) }
    var f1SignedPercent: String { String(format: "%+.1f%%", self * 100) }
    var f1Odds: String { String(format: "%.2f", self) }
}
