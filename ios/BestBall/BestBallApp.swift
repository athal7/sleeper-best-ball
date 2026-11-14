import SwiftUI
import BestBallKit

@main
struct BestBallApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .task { await model.start() }
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            if model.isConnected {
                MatchupsView()
            } else {
                SetupView()
            }
        }
        .animation(.default, value: model.isConnected)
    }
}
