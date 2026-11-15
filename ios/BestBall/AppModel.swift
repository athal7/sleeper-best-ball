import Combine
import Foundation
import BestBallKit
#if canImport(WidgetKit)
import WidgetKit
#endif

@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var config: SavedLeague?
    @Published private(set) var week: LeagueWeek?
    @Published private(set) var state: SportState?
    @Published private(set) var isLoading = false
    @Published private(set) var isConnecting = false
    @Published var errorMessage: String?

    @Published var username = ""
    @Published private(set) var leagues: [LeagueSummary] = []
    @Published var setupError: String?

    @Published private(set) var isTrackingLiveActivity = LiveActivityController.shared.isTracking

    private let service = BestBallService()
    private let liveActivities = LiveActivityController.shared
    private var account: SleeperAccount?
    private var snapshot: WidgetSnapshot?
    private var hasStarted = false

    /// Set when the user dismisses the Live Activity so refreshes don't bring it
    /// back until they ask for it again.
    private static let liveActivityMutedKey = "bestball.liveActivityMuted"

    static let weeks = 1...18

    var isConnected: Bool { config != nil }
    var currentSeason: Int {
        state.flatMap { Int($0.leagueSeason) } ?? Calendar.current.component(.year, from: Date())
    }

    // MARK: Lifecycle

    func start() async {
        guard !hasStarted else { return }
        hasStarted = true
        config = SharedStore.loadConfig()
        state = try? await service.sportState()
        if let config {
            username = config.username
            await load(week: config.week)
        }
    }

    // MARK: Setup

    func connect() async {
        let name = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else {
            setupError = "Enter your Sleeper username."
            return
        }
        isConnecting = true
        setupError = nil
        defer { isConnecting = false }

        do {
            if state == nil { state = try await service.sportState() }
            let result = try await service.lookup(username: name, season: currentSeason)
            account = result.account
            leagues = result.leagues.sorted(by: Self.leagueOrder)
            if leagues.isEmpty {
                setupError = "No \(currentSeason) NFL leagues found for that account."
            }
        } catch {
            setupError = message(for: error)
        }
    }

    func selectLeague(_ league: LeagueSummary) async {
        guard let account else { return }
        let season = Int(league.season) ?? currentSeason
        let config = SavedLeague(
            username: account.displayName ?? account.username ?? username,
            userID: account.userID,
            leagueID: league.leagueID,
            leagueName: league.name,
            season: season,
            week: state?.defaultWeek ?? 1
        )
        self.config = config
        username = config.username
        SharedStore.saveConfig(config)
        await load(week: config.week)
    }

    func signOut() {
        SharedStore.clearConfig()
        config = nil
        week = nil
        leagues = []
        account = nil
        username = ""
        errorMessage = nil
        snapshot = nil
        isTrackingLiveActivity = false
        Task { await liveActivities.end() }
    }

    // MARK: Live Activity

    /// Starts or stops the Live Activity that tracks this matchup's score.
    func toggleLiveActivity() async {
        if liveActivities.isTracking {
            await liveActivities.end()
            UserDefaults.standard.set(true, forKey: Self.liveActivityMutedKey)
        } else {
            UserDefaults.standard.set(false, forKey: Self.liveActivityMutedKey)
            if let snapshot { await liveActivities.sync(snapshot) }
        }
        isTrackingLiveActivity = liveActivities.isTracking
    }

    // MARK: Weeks

    func load(week targetWeek: Int) async {
        guard let config else { return }
        let clamped = min(max(targetWeek, Self.weeks.lowerBound), Self.weeks.upperBound)
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let loaded = try await service.loadWeek(
                leagueID: config.leagueID,
                week: clamped,
                userID: config.userID
            )
            week = loaded

            var updated = config
            updated.week = clamped
            self.config = updated
            SharedStore.saveConfig(updated)

            if let snapshot = loaded.widgetSnapshot() {
                SharedStore.saveSnapshot(snapshot)
                self.snapshot = snapshot
                #if canImport(WidgetKit)
                WidgetCenter.shared.reloadAllTimelines()
                #endif
                await updateLiveActivity(snapshot, week: clamped)
            }
        } catch {
            errorMessage = message(for: error)
        }
    }

    func refresh() async {
        await load(week: week?.week ?? config?.week ?? 1)
    }

    func showPreviousWeek() async {
        await load(week: (week?.week ?? config?.week ?? 1) - 1)
    }

    func showNextWeek() async {
        await load(week: (week?.week ?? config?.week ?? 1) + 1)
    }

    /// Tracks the current week automatically; other weeks only refresh an
    /// activity that's already running.
    private func updateLiveActivity(_ snapshot: WidgetSnapshot, week: Int) async {
        let muted = UserDefaults.standard.bool(forKey: Self.liveActivityMutedKey)
        if liveActivities.isTracking {
            await liveActivities.sync(snapshot)
        } else if !muted, week == state?.defaultWeek {
            await liveActivities.sync(snapshot)
        }
        isTrackingLiveActivity = liveActivities.isTracking
    }

    // MARK: Helpers

    private func message(for error: Error) -> String {
        if let localized = error as? LocalizedError, let description = localized.errorDescription {
            return description
        }
        return error.localizedDescription
    }

    /// Leagues that are currently playing come first, then drafts, then finished ones.
    private static func leagueOrder(_ lhs: LeagueSummary, _ rhs: LeagueSummary) -> Bool {
        let lhsRank = statusRank(lhs.status)
        let rhsRank = statusRank(rhs.status)
        if lhsRank != rhsRank { return lhsRank < rhsRank }
        return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
    }

    private static func statusRank(_ status: String) -> Int {
        switch status {
        case "in_season": return 0
        case "drafting": return 1
        case "pre_draft": return 2
        case "complete": return 3
        default: return 4
        }
    }
}
