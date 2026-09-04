import SwiftUI

struct RootView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationSplitView {
            List(AppSection.allCases, selection: $model.selection) { section in
                Label(section.rawValue, systemImage: section.systemImage)
                    .tag(section)
            }
            .navigationTitle("Football 1")
            .safeAreaInset(edge: .bottom) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(model.isPreview ? "PREVIEW MODE" : "LIVE DATA")
                        .font(.caption.bold())
                    Text(model.snapshotLabel)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.bar)
            }
        } detail: {
            content
                .navigationTitle(model.selection?.rawValue ?? "Football 1")
        }
    }

    @ViewBuilder
    private var content: some View {
        switch model.selection ?? .live {
        case .live:
            LiveView()
        case .mispricing:
            MispricingView()
        case .ledger:
            LedgerView()
        case .research:
            ResearchView()
        case .data:
            DataView()
        }
    }
}
