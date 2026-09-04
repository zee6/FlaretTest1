import Foundation

enum AppSection: String, CaseIterable, Identifiable {
    case live = "Live"
    case mispricing = "Mispricing"
    case ledger = "Ledger"
    case research = "Research"
    case data = "Data"

    var id: String { rawValue }

    var systemImage: String {
        switch self {
        case .live: "sportscourt"
        case .mispricing: "scope"
        case .ledger: "checkmark.seal"
        case .research: "chart.line.uptrend.xyaxis"
        case .data: "externaldrive"
        }
    }
}

enum MatchOutcome: String, CaseIterable, Identifiable {
    case home = "H"
    case draw = "D"
    case away = "A"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .home: "Home"
        case .draw: "Draw"
        case .away: "Away"
        }
    }
}

struct OutcomeQuote: Identifiable, Hashable {
    let outcome: MatchOutcome
    let marketProbability: Double
    let football1Probability: Double
    let bestOdds: Double

    var id: MatchOutcome { outcome }
    var probabilityEdge: Double { football1Probability - marketProbability }
    var predictedEV: Double { football1Probability * bestOdds - 1.0 }
}

struct FixtureRow: Identifiable, Hashable {
    let id: String
    let kickoff: Date
    let homeTeam: String
    let awayTeam: String
    let bookmakerCount: Int
    let status: String
    let quotes: [OutcomeQuote]

    var strongestQuote: OutcomeQuote? {
        quotes.max { $0.predictedEV < $1.predictedEV }
    }
}

struct LedgerRow: Identifiable, Hashable {
    let id: String
    let timestamp: Date
    let fixture: String
    let selection: String
    let bestOdds: Double
    let predictedEV: Double
    let state: String
    let pnl: Double?
}

struct ResearchMetric: Identifiable, Hashable {
    let id = UUID()
    let title: String
    let value: String
    let detail: String
}

struct DataHealthRow: Identifiable, Hashable {
    let id = UUID()
    let source: String
    let status: String
    let detail: String
}

extension Double {
    var percent1: String { String(format: "%.1f%%", self * 100) }
    var signedPercent1: String { String(format: "%+.1f%%", self * 100) }
    var odds2: String { String(format: "%.2f", self) }
}
