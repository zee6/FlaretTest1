import Foundation

// Run with swiftc alongside ResultsData.swift, without SwiftUI or network access.
@main
enum ResultsContractTests {
    static func main() throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let feed = try ResultsFeed.decode(data)
        precondition(!feed.batches.isEmpty)
        let october = feed.batches.first { $0.startDate == "2026-10-10" }
        precondition(october?.matches.count == 9)
        for batch in feed.batches {
            precondition(batch.settledCount + batch.pendingCount == batch.matches.count)
            precondition(!batch.dateLabel.isEmpty)
            for match in batch.matches {
                precondition(!match.selectionName.isEmpty)
                precondition(!ResultsDate.timestamp(match.kickoffUtc).isEmpty)
            }
        }
        let original = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        func rejects(_ mutation: (inout [String: Any]) -> Void) throws {
            var changed = original
            mutation(&changed)
            let bytes = try JSONSerialization.data(withJSONObject: changed)
            do {
                _ = try ResultsFeed.decode(bytes)
                fatalError("Invalid results feed was accepted")
            } catch { /* Expected: no partial or silently zero-filled results. */ }
        }
        try rejects { $0["schema_version"] = 2 }
        try rejects { $0["official_policy"] = "active" }
        try rejects { $0.removeValue(forKey: "batches") }
        try rejects { root in
            var batches = root["batches"] as! [[String: Any]]
            batches[0]["settled_count"] = 100
            root["batches"] = batches
        }
        try rejects { root in
            var batches = root["batches"] as! [[String: Any]]
            let batchIndex = batches.firstIndex { ($0["settled_count"] as! Int) > 0 }!
            var matches = batches[batchIndex]["matches"] as! [[String: Any]]
            var result = matches.first(where: { $0["settlement"] is [String: Any] })!["settlement"] as! [String: Any]
            result["pnl_units"] = 99.0
            let index = matches.firstIndex(where: { $0["settlement"] is [String: Any] })!
            matches[index]["settlement"] = result
            batches[batchIndex]["matches"] = matches
            root["batches"] = batches
        }
        // A legitimate all-pending slate must decode without inventing metrics.
        var pending = original
        var batches = pending["batches"] as! [[String: Any]]
        for index in batches.indices {
            var matches = batches[index]["matches"] as! [[String: Any]]
            for match in matches.indices { matches[match]["settlement"] = NSNull() }
            batches[index]["matches"] = matches
            batches[index]["settled_count"] = 0
            batches[index]["pending_count"] = matches.count
            batches[index]["scoring"] = ["model_log_loss": NSNull(), "market_log_loss": NSNull(), "model_brier": NSNull(), "market_brier": NSNull()]
            batches[index]["diagnostic"] = ["stake_units": 0, "pnl_units": 0, "roi": NSNull(), "wins": 0, "max_drawdown_units": 0]
        }
        pending["batches"] = batches
        pending["last_settlement_at_utc"] = NSNull()
        _ = try ResultsFeed.decode(JSONSerialization.data(withJSONObject: pending))
        var empty = original
        empty["batches"] = []
        empty["last_settlement_at_utc"] = NSNull()
        let emptyFeed = try ResultsFeed.decode(JSONSerialization.data(withJSONObject: empty))
        precondition(emptyFeed.batches.isEmpty)
        print("Results Swift contract checks passed")
    }
}
