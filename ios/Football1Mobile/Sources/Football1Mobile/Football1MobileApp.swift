import SwiftUI
import PhotosUI
import Vision
import UIKit

@main
struct Football1MobileApp: App {
    var body: some Scene {
        WindowGroup {
            Football1AskShell()
        }
    }
}

private enum AskTheme {
    static let background = Color(red: 0.025, green: 0.032, blue: 0.050)
    static let panel = Color.white.opacity(0.075)
    static let panelStrong = Color.white.opacity(0.11)
    static let stroke = Color.white.opacity(0.12)
    static let text = Color.white
    static let secondary = Color.white.opacity(0.60)
    static let tertiary = Color.white.opacity(0.36)
    static let accent = Color(red: 0.42, green: 0.72, blue: 1.0)
    static let positive = Color(red: 0.39, green: 0.88, blue: 0.67)
    static let caution = Color(red: 0.98, green: 0.72, blue: 0.32)
}

private struct Football1AskShell: View {
    @State private var showAsk = false

    var body: some View {
        ContentView()
            .overlay(alignment: .bottom) {
                Button {
                    showAsk = true
                } label: {
                    HStack(spacing: 9) {
                        Image(systemName: "sparkles")
                            .font(.caption.weight(.bold))
                        Text("ASK FOOTBALL 1")
                            .font(.caption.weight(.bold))
                            .tracking(1.0)
                        Spacer(minLength: 4)
                        Image(systemName: "chevron.up")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(AskTheme.secondary)
                    }
                    .foregroundStyle(AskTheme.text)
                    .padding(.horizontal, 16)
                    .frame(height: 48)
                    .background(
                        Capsule()
                            .fill(.ultraThinMaterial)
                            .overlay(Capsule().fill(AskTheme.background.opacity(0.58)))
                    )
                    .overlay(
                        Capsule()
                            .stroke(AskTheme.accent.opacity(0.35), lineWidth: 1)
                    )
                    .shadow(color: .black.opacity(0.32), radius: 18, y: 8)
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 44)
                .padding(.bottom, 62)
            }
            .sheet(isPresented: $showAsk) {
                AskFootball1Sheet()
                    .presentationDetents([.fraction(0.72), .large])
                    .presentationDragIndicator(.visible)
                    .presentationBackground(AskTheme.background)
            }
    }
}

private struct AskFootball1Sheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var fixtures = MobilePreviewData.fixtures
    @State private var selectedFixtureID = MobilePreviewData.fixtures[0].id
    @State private var query = ""
    @State private var answer: String?
    @State private var screenshotItem: PhotosPickerItem?
    @State private var scanMessage: String?
    @FocusState private var queryFocused: Bool

    private var fixture: MobileFixture {
        fixtures.first { $0.id == selectedFixtureID } ?? fixtures[0]
    }

    private var call: MobileOutcome { fixture.mostLikelyOutcome }

    var body: some View {
        ZStack {
            AskTheme.background.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    fixtureContext
                    quickPrompts
                    askField
                    if let answer {
                        responseCard(answer)
                    }
                    checkABetCard
                    capabilityNote
                    Spacer(minLength: 34)
                }
                .padding(.horizontal, 18)
                .padding(.top, 8)
            }
        }
        .preferredColorScheme(.dark)
        .task {
            await loadLiveFixtures()
        }
        .onChange(of: screenshotItem) { _, newItem in
            guard let newItem else { return }
            Task { await readScreenshot(newItem) }
        }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("FOOTBALL 1")
                    .font(.caption2.weight(.bold))
                    .tracking(1.8)
                    .foregroundStyle(AskTheme.accent)
                Text("Ask anything.")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                    .foregroundStyle(AskTheme.text)
                Text("Match context, price questions, or a bet you want checked.")
                    .font(.subheadline)
                    .foregroundStyle(AskTheme.secondary)
            }
            Spacer()
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(AskTheme.secondary)
                    .frame(width: 34, height: 34)
                    .background(Circle().fill(AskTheme.panel))
            }
            .buttonStyle(.plain)
        }
    }

    private var fixtureContext: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("MATCH CONTEXT")
                        .font(.caption2.weight(.bold))
                        .tracking(1.3)
                        .foregroundStyle(AskTheme.tertiary)
                    Text("\(fixture.home) · \(fixture.away)")
                        .font(.headline)
                        .foregroundStyle(AskTheme.text)
                    Text("Our call: \(call.name) \(call.football1.f1Percent)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AskTheme.accent)
                }
                Spacer()
                Menu {
                    ForEach(fixtures) { item in
                        Button("\(item.home) v \(item.away)") {
                            selectedFixtureID = item.id
                            answer = nil
                        }
                    }
                } label: {
                    Image(systemName: "arrow.up.arrow.down")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(AskTheme.accent)
                        .frame(width: 34, height: 34)
                        .background(Circle().fill(AskTheme.accent.opacity(0.11)))
                }
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(AskTheme.panel))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(AskTheme.stroke, lineWidth: 1))
    }

    private var quickPrompts: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                PromptChip(title: "Who wins?", icon: "scope") {
                    submit("Who do you think wins?")
                }
                PromptChip(title: "Why?", icon: "questionmark") {
                    submit("Why is that your call?")
                }
                PromptChip(title: "Fair odds?", icon: "sterlingsign") {
                    submit("What odds would you need?")
                }
                PromptChip(title: "Check a bet", icon: "viewfinder") {
                    query = "Check this bet: "
                    answer = nil
                    queryFocused = true
                }
            }
        }
    }

    private var askField: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Ask Football 1…", text: $query, axis: .vertical)
                .lineLimit(1...5)
                .focused($queryFocused)
                .textInputAutocapitalization(.sentences)
                .submitLabel(.send)
                .onSubmit { submit(query) }
                .font(.body)
                .foregroundStyle(AskTheme.text)

            Button {
                submit(query)
            } label: {
                Image(systemName: "arrow.up")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(AskTheme.background)
                    .frame(width: 38, height: 38)
                    .background(Circle().fill(query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? AskTheme.tertiary : AskTheme.accent))
            }
            .buttonStyle(.plain)
            .disabled(query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 20, style: .continuous).fill(AskTheme.panelStrong))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(AskTheme.accent.opacity(queryFocused ? 0.48 : 0.18), lineWidth: 1))
    }

    private func responseCard(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 7) {
                Circle().fill(AskTheme.accent).frame(width: 6, height: 6)
                Text("FOOTBALL 1")
                    .font(.caption2.weight(.bold))
                    .tracking(1.2)
                    .foregroundStyle(AskTheme.accent)
            }
            Text(text)
                .font(.body.weight(.medium))
                .foregroundStyle(AskTheme.text.opacity(0.94))
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(AskTheme.accent.opacity(0.075))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(AskTheme.accent.opacity(0.22), lineWidth: 1)
        )
    }

    private var checkABetCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("BET REALITY CHECK")
                        .font(.caption2.weight(.bold))
                        .tracking(1.4)
                        .foregroundStyle(AskTheme.caution)
                    Text("Get the bet into Football 1")
                        .font(.headline)
                        .foregroundStyle(AskTheme.text)
                }
                Spacer()
                Image(systemName: "viewfinder")
                    .foregroundStyle(AskTheme.caution)
            }

            HStack(spacing: 10) {
                PhotosPicker(selection: $screenshotItem, matching: .images) {
                    IntakeButtonLabel(icon: "photo", title: "SCAN SCREENSHOT")
                }
                .buttonStyle(.plain)

                Button {
                    pasteBet()
                } label: {
                    IntakeButtonLabel(icon: "doc.on.clipboard", title: "PASTE")
                }
                .buttonStyle(.plain)
            }

            if let scanMessage {
                Text(scanMessage)
                    .font(.caption)
                    .foregroundStyle(AskTheme.secondary)
            } else {
                Text("Screenshot text is read on-device. Paste works for copied bet slips or bookmaker text.")
                    .font(.caption)
                    .foregroundStyle(AskTheme.secondary)
            }
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 22, style: .continuous).fill(AskTheme.panel))
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(AskTheme.caution.opacity(0.20), lineWidth: 1))
    }

    private var capabilityNote: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("NOW")
                .font(.caption2.weight(.bold))
                .tracking(1.2)
                .foregroundStyle(AskTheme.tertiary)
            Text("Football 1 can answer the current 1X2 call and price questions immediately, and it can capture complex-bet text from a screenshot or clipboard.")
                .font(.caption)
                .foregroundStyle(AskTheme.secondary)
            Text("For exotic multi-leg bets, the joint-probability engine is not connected yet. Until it is calibrated, Football 1 will capture the bet but will not invent a fair price.")
                .font(.caption.weight(.semibold))
                .foregroundStyle(AskTheme.secondary)
        }
    }

    private func submit(_ raw: String) {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        query = trimmed
        answer = localAnswer(for: trimmed)
        queryFocused = false
    }

    private func localAnswer(for raw: String) -> String {
        let text = raw.lowercased()
        let fairOdds = call.fairOdds.f1Odds
        let currentOdds = call.odds.f1Odds
        let home = fixture.outcomes.first { $0.id == "H" }!
        let draw = fixture.outcomes.first { $0.id == "D" }!
        let away = fixture.outcomes.first { $0.id == "A" }!

        if looksLikeComplexBet(text) {
            return "I can read this as a multi-condition bet. I have captured the text, but I will not quote a 'realistic' price until the joint-event model for its legs is connected and calibrated. That is exactly what Bet Reality Check will do."
        }

        if text.contains("why") {
            let direction = call.football1 - call.market
            let marketPhrase = direction >= 0
                ? "slightly above the market's \(call.market.f1Percent)"
                : "slightly below the market's \(call.market.f1Percent)"
            return "\(call.name) is the single most likely result at \(call.football1.f1Percent), \(marketPhrase). Home / draw / away are \(home.football1.f1Percent), \(draw.football1.f1Percent), and \(away.football1.f1Percent). The call is about probability; the price decision is separate."
        }

        if text.contains("odds") || text.contains("price") || text.contains("fair") {
            if call.ev > 0 {
                return "For \(call.name), Football 1's fair price is about \(fairOdds). The quoted price in the locked snapshot is \(currentOdds), so it sits above our fair line. That is price interest, not a validated staking instruction."
            }
            return "For \(call.name), Football 1's fair price is about \(fairOdds). The quoted price in the locked snapshot is \(currentOdds), which is too short for our \(call.football1.f1Percent) estimate. Likely winner; wrong price."
        }

        if text.contains("win") || text.contains("result") || text.contains("call") || text.contains("who") {
            if call.id == "D" {
                return "The draw is Football 1's single most likely result at \(call.football1.f1Percent). Home is \(home.football1.f1Percent) and away is \(away.football1.f1Percent)."
            }
            return "Football 1 makes \(call.name) the most likely winner at \(call.football1.f1Percent). The draw is \(draw.football1.f1Percent); the other team is \((call.id == "H" ? away : home).football1.f1Percent)."
        }

        return "For \(fixture.home) v \(fixture.away), our result call is \(call.name) at \(call.football1.f1Percent). Fair odds on that call are about \(fairOdds). Ask 'why?', 'fair odds?', or paste a bet and I will route it to the right view."
    }

    private func looksLikeComplexBet(_ text: String) -> Bool {
        let markers = [
            "check this bet", "btts", "both teams", "red card", "to score", "scorer",
            "shots on target", "corners", "cards", "bet builder", "same game", " + ", " and "
        ]
        let hits = markers.filter { text.contains($0) }.count
        return hits >= 1 && (text.contains("bet") || hits >= 2)
    }

    private func pasteBet() {
        guard let pasted = UIPasteboard.general.string,
              !pasted.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            scanMessage = "There is no text on the clipboard to read."
            return
        }
        query = pasted
        scanMessage = "Bet text pasted. Review it, then tap the arrow to check it."
        answer = nil
        queryFocused = true
    }

    @MainActor
    private func readScreenshot(_ item: PhotosPickerItem) async {
        scanMessage = "Reading screenshot on-device…"
        do {
            guard let data = try await item.loadTransferable(type: Data.self),
                  let uiImage = UIImage(data: data),
                  let cgImage = uiImage.cgImage else {
                scanMessage = "I could not read that image."
                return
            }

            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = true
            let handler = VNImageRequestHandler(cgImage: cgImage)
            try handler.perform([request])

            let text = (request.results ?? [])
                .compactMap { $0.topCandidates(1).first?.string }
                .joined(separator: "\n")
                .trimmingCharacters(in: .whitespacesAndNewlines)

            guard !text.isEmpty else {
                scanMessage = "No readable text was found in that screenshot."
                return
            }

            query = text
            answer = nil
            scanMessage = "Screenshot read. Review the captured bet, then tap the arrow to check it."
            queryFocused = true
        } catch {
            scanMessage = "I could not read that screenshot."
        }
    }

    @MainActor
    private func loadLiveFixtures() async {
        do {
            let live = try await MobileLiveData.loadProspectiveFixtures()
            guard !live.isEmpty else { return }
            fixtures = live
            selectedFixtureID = live[0].id
        } catch {
            // The Ask surface remains useful with preview fixtures if the public ledger is unavailable.
        }
    }
}

private struct PromptChip: View {
    let title: String
    let icon: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                Text(title)
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(AskTheme.text)
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(Capsule().fill(AskTheme.panel))
            .overlay(Capsule().stroke(AskTheme.stroke, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

private struct IntakeButtonLabel: View {
    let icon: String
    let title: String

    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: icon)
            Text(title)
                .font(.caption2.weight(.bold))
                .tracking(0.5)
        }
        .foregroundStyle(AskTheme.text)
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(AskTheme.panelStrong))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(AskTheme.stroke, lineWidth: 1))
    }
}
