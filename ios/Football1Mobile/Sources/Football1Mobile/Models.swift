import Foundation

struct MobileOutcome: Identifiable, Hashable, Sendable {
    let id: String
    let name: String
    let market: Double
    let elo: Double
    let poisson: Double
    let football1: Double
    let odds: Double

    var breakEven: Double { 1.0 / odds }
    var fairOdds: Double { 1.0 / football1 }
    var ev: Double { football1 * odds - 1.0 }
    var edge: Double { football1 - market }
}

struct MobileFixture: Identifiable, Hashable, Sendable {
    let id: String
    let kickoff: String
    let home: String
    let away: String
    let bookmakerCount: Int
    let isProspective: Bool
    let snapshotRetrievedAt: String?
    let outcomes: [MobileOutcome]

    var mostLikelyOutcome: MobileOutcome {
        outcomes.max { $0.football1 < $1.football1 } ?? outcomes[0]
    }

    var bestPriceOutcome: MobileOutcome {
        outcomes.max { $0.ev < $1.ev } ?? outcomes[0]
    }

    // Kept as a compatibility alias for older views while the interface migrates
    // to the clearer `bestPriceOutcome` name.
    var strongestOutcome: MobileOutcome { bestPriceOutcome }
}

enum MobileLiveData {
    static let ledgerURL = URL(string: "https://raw.githubusercontent.com/zee6/FlaretTest1/master/prospective/ledger.jsonl")!

    static func loadProspectiveFixtures(now: Date = Date()) async throws -> [MobileFixture] {
        let (data, response) = try await URLSession.shared.data(from: ledgerURL)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        guard let text = String(data: data, encoding: .utf8) else {
            throw URLError(.cannotDecodeRawData)
        }

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        var latestByEvent: [String: LedgerPrediction] = [:]

        for line in text.split(whereSeparator: \.isNewline) {
            guard let lineData = String(line).data(using: .utf8),
                  let record = try? decoder.decode(LedgerPrediction.self, from: lineData),
                  record.status == "prediction_locked",
                  let kickoff = parseISO8601(record.commenceTimeUtc),
                  kickoff > now else {
                continue
            }

            if let existing = latestByEvent[record.eventId],
               let existingTime = parseISO8601(existing.snapshotRetrievedAtUtc),
               let newTime = parseISO8601(record.snapshotRetrievedAtUtc),
               existingTime >= newTime {
                continue
            }
            latestByEvent[record.eventId] = record
        }

        return latestByEvent.values.compactMap { record in
            guard let kickoffDate = parseISO8601(record.commenceTimeUtc) else { return nil }
            let market = record.marketAnchor.probability
            let model = record.model.probability
            let odds = record.marketAnchor.bestDecimalOdds

            return MobileFixture(
                id: record.eventId,
                kickoff: kickoffLabel(kickoffDate),
                home: record.homeTeamProvider,
                away: record.awayTeamProvider,
                bookmakerCount: record.completeH2HBookmakerCount,
                isProspective: true,
                snapshotRetrievedAt: record.snapshotRetrievedAtUtc,
                outcomes: [
                    MobileOutcome(id: "H", name: record.homeTeamProvider, market: market.home, elo: .nan, poisson: .nan, football1: model.home, odds: odds.home),
                    MobileOutcome(id: "D", name: "Draw", market: market.draw, elo: .nan, poisson: .nan, football1: model.draw, odds: odds.draw),
                    MobileOutcome(id: "A", name: record.awayTeamProvider, market: market.away, elo: .nan, poisson: .nan, football1: model.away, odds: odds.away)
                ]
            )
        }
        .sorted {
            guard let lhs = latestByEvent[$0.id].flatMap({ parseISO8601($0.commenceTimeUtc) }),
                  let rhs = latestByEvent[$1.id].flatMap({ parseISO8601($0.commenceTimeUtc) }) else {
                return $0.id < $1.id
            }
            return lhs < rhs
        }
    }

    private static func parseISO8601(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) { return date }

        let standard = ISO8601DateFormatter()
        standard.formatOptions = [.withInternetDateTime]
        return standard.date(from: value)
    }

    private static func kickoffLabel(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_GB")
        formatter.timeZone = .current
        formatter.dateFormat = "EEE · HH:mm zzz"
        return formatter.string(from: date)
    }
}

private struct LedgerPrediction: Decodable {
    let eventId: String
    let commenceTimeUtc: String
    let snapshotRetrievedAtUtc: String
    let homeTeamProvider: String
    let awayTeamProvider: String
    let completeH2HBookmakerCount: Int
    let status: String
    let marketAnchor: LedgerMarketAnchor
    let model: LedgerModel
}

private struct LedgerMarketAnchor: Decodable {
    let probability: LedgerTriple
    let bestDecimalOdds: LedgerTriple
}

private struct LedgerModel: Decodable {
    let probability: LedgerTriple
}

private struct LedgerTriple: Decodable {
    let home: Double
    let draw: Double
    let away: Double
}

enum MobilePreviewData {
    static let fixtures: [MobileFixture] = [
        MobileFixture(
            id: "newcastle-bournemouth",
            kickoff: "Sat · 11:30 UTC",
            home: "Newcastle United",
            away: "Bournemouth",
            bookmakerCount: 21,
            isProspective: false,
            snapshotRetrievedAt: nil,
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
            isProspective: false,
            snapshotRetrievedAt: nil,
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
            isProspective: false,
            snapshotRetrievedAt: nil,
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
