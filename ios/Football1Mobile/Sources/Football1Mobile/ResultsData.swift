import Foundation

struct ResultsFeed: Decodable, Sendable {
    let schemaVersion: Int
    let officialPolicy: String
    let lastSettlementAtUtc: String?
    let batches: [ResultsBatch]

    static let url = URL(string: "https://raw.githubusercontent.com/zee6/FlaretTest1/master/prospective/mobile_results.json")!

    static var usesBundledPreview: Bool {
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--results-preview")
        #else
        return false
        #endif
    }

    static func load() async throws -> ResultsFeed {
        if usesBundledPreview {
            guard let file = Bundle.main.url(forResource: "mobile_results", withExtension: "json") else {
                throw ResultsDataError.invalidFeed
            }
            return try decode(Data(contentsOf: file))
        }
        let request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 25)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return try decode(data)
    }

    static func decode(_ data: Data) throws -> ResultsFeed {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let feed = try decoder.decode(ResultsFeed.self, from: data)
        guard feed.schemaVersion == 1, feed.officialPolicy == "no_validated_betting_rule",
              Set(feed.batches.map(\.id)).count == feed.batches.count,
              feed.lastSettlementAtUtc.map({ ResultsDate.parse($0) != nil }) ?? true else {
            throw ResultsDataError.invalidFeed
        }
        for batch in feed.batches { try batch.validate() }
        return feed
    }
}

enum ResultsDataError: Error {
    case invalidFeed
}

struct ResultsBatch: Decodable, Identifiable, Sendable {
    let id: String
    let frozenAtUtc: String
    let startDate: String
    let endDate: String
    let settledCount: Int
    let pendingCount: Int
    let scoring: ResultsScoring
    let diagnostic: ResultsDiagnostic
    let matches: [ResultsMatch]

    var dateLabel: String {
        let start = ResultsDate.day(startDate)
        return startDate == endDate ? start : "\(start) – \(ResultsDate.day(endDate))"
    }

    func validate() throws {
        let settled = matches.compactMap(\.settlement)
        guard !matches.isEmpty, let freeze = ResultsDate.parse(frozenAtUtc),
              Set(matches.map(\.id)).count == matches.count,
              settledCount == settled.count, pendingCount == matches.count - settledCount,
              diagnostic.stakeUnits == settledCount,
              diagnostic.wins == matches.filter({ $0.settlement?.outcome == $0.selection }).count,
              diagnostic.maxDrawdownUnits.isFinite, diagnostic.maxDrawdownUnits >= 0,
              abs(diagnostic.pnlUnits - settled.reduce(0) { $0 + $1.pnlUnits }) < 1e-8 else {
            throw ResultsDataError.invalidFeed
        }
        let scores = [scoring.modelLogLoss, scoring.marketLogLoss, scoring.modelBrier, scoring.marketBrier]
        if settledCount == 0 {
            guard scores.allSatisfy({ $0 == nil }), diagnostic.roi == nil else { throw ResultsDataError.invalidFeed }
        } else {
            guard scores.allSatisfy({ $0.map { $0.isFinite && $0 >= 0 } ?? false }),
                  let roi = diagnostic.roi,
                  abs(roi - diagnostic.pnlUnits / Double(settledCount)) < 1e-8 else { throw ResultsDataError.invalidFeed }
        }
        for match in matches {
            guard let kickoff = ResultsDate.parse(match.kickoffUtc), kickoff > freeze,
                  match.modelProbability.isProbability, match.marketProbability.isProbability,
                  match.odds.values.allSatisfy({ $0.isFinite && $0 > 1 }),
                  ["home", "draw", "away"].contains(match.selection),
                  match.predictedEv.isFinite else { throw ResultsDataError.invalidFeed }
            if let result = match.settlement {
                let outcome = result.homeScore > result.awayScore ? "home" : result.homeScore < result.awayScore ? "away" : "draw"
                let expected = outcome == match.selection ? match.odds.value(for: outcome) - 1 : -1
                guard result.homeScore >= 0, result.awayScore >= 0, result.outcome == outcome,
                      let recorded = ResultsDate.parse(result.recordedAtUtc), recorded > kickoff,
                      abs(result.pnlUnits - expected) < 1e-8 else { throw ResultsDataError.invalidFeed }
            }
        }
    }
}

struct ResultsScoring: Decodable, Sendable {
    let modelLogLoss: Double?
    let marketLogLoss: Double?
    let modelBrier: Double?
    let marketBrier: Double?
}

struct ResultsDiagnostic: Decodable, Sendable {
    let stakeUnits: Int
    let pnlUnits: Double
    let roi: Double?
    let wins: Int
    let maxDrawdownUnits: Double
}

struct ResultsMatch: Decodable, Identifiable, Sendable {
    let id: String
    let home: String
    let away: String
    let kickoffUtc: String
    let modelProbability: ResultsTriple
    let marketProbability: ResultsTriple
    let odds: ResultsTriple
    let selection: String
    let predictedEv: Double
    let settlement: ResultsSettlement?

    var selectionName: String { selection == "home" ? home : selection == "away" ? away : "Draw" }
}

struct ResultsSettlement: Decodable, Sendable {
    let homeScore: Int
    let awayScore: Int
    let outcome: String
    let pnlUnits: Double
    let recordedAtUtc: String
}

struct ResultsTriple: Decodable, Sendable {
    let home: Double
    let draw: Double
    let away: Double

    var values: [Double] { [home, draw, away] }
    var isProbability: Bool { values.allSatisfy { $0.isFinite && $0 > 0 && $0 < 1 } && abs(values.reduce(0, +) - 1) < 1e-6 }
    func value(for outcome: String) -> Double { outcome == "home" ? home : outcome == "away" ? away : draw }
}

enum ResultsDate {
    static func parse(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
    }

    static func timestamp(_ value: String) -> String {
        guard let date = parse(value) else { return value }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_GB")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "d MMM yyyy · HH:mm 'UTC'"
        return formatter.string(from: date)
    }

    static func day(_ value: String) -> String {
        guard let date = parse(value + "T00:00:00Z") else { return value }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_GB")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "d MMM yyyy"
        return formatter.string(from: date)
    }
}
