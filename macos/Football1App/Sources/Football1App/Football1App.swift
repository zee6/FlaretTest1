import SwiftUI

@main
struct Football1App: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup("Football 1") {
            RootView()
                .environmentObject(model)
                .frame(minWidth: 1080, minHeight: 680)
        }
        .defaultSize(width: 1320, height: 820)
    }
}
