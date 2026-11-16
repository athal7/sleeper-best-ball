import SwiftUI
import UIKit
import BackgroundTasks
import BestBallKit

@main
struct BestBallApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .task { await model.start() }
        }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        // Must be registered before launch finishes or the scheduler refuses to run it.
        BackgroundRefresh.register()
        return true
    }
}

/// Wakes the app up periodically so the Live Activities keep moving without you
/// opening it. iOS decides exactly when; this only asks for roughly every 15
/// minutes and gets whatever the system allows.
@MainActor
enum BackgroundRefresh {
    static var identifier: String {
        (Bundle.main.bundleIdentifier ?? "com.sleeperbestball.app") + ".refresh"
    }

    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: identifier, using: nil) { task in
            guard let task = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }
            Task { @MainActor in await run(task) }
        }
    }

    /// Always keep one request in flight; a second submit while one is pending is
    /// rejected, which is fine because the pending one already covers us.
    static func schedule() {
        guard SharedStore.loadUsername() != nil else { return }
        let request = BGAppRefreshTaskRequest(identifier: identifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(request)
    }

    static func cancel() {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: identifier)
    }

    private static func run(_ task: BGAppRefreshTask) async {
        // Queue the next wake-up before doing any work, so one slow network call
        // can't end the chain.
        schedule()

        guard SharedStore.loadUsername() != nil,
              !UserDefaults.standard.bool(forKey: AppModel.liveActivityMutedKey) else {
            task.setTaskCompleted(success: true)
            return
        }

        let work = Task { @MainActor in
            let model = AppModel()
            await model.start()
            // start() also scans waivers, which is what posts the notification.
            return model.errorMessage == nil
        }
        task.expirationHandler = { work.cancel() }
        let success = await work.value
        task.setTaskCompleted(success: success)
    }
}

struct RootView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        Group {
            if model.isConnected {
                MatchupsView()
            } else {
                SetupView()
            }
        }
        .animation(.default, value: model.isConnected)
        .onChange(of: scenePhase) { _, phase in
            if phase == .background {
                model.didEnterBackground()
            }
        }
    }
}
