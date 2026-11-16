import Combine
import Foundation
import BestBallKit
#if canImport(WidgetKit)
import WidgetKit
#endif

@MainActor
final class AppModel: ObservableObject {
    /// Every league you're in, scored for the week you're looking at.
    @Published private(set) var leagueWeeks: [LeagueWeek] = []
    @Published private(set) var week = 1
    @Published private(set) var state: SportState?
    @Published private(set) var isLoading = false
    @Published private(set) var isConnecting = false
    @Published private(set) var isConnected = false
    @Published var errorMessage: String?

    @Published var username = ""
    @Published private(set) var leagues: [LeagueSummary] = []
    @Published var setupError: String?

    /// The scores start on your own games; the full slate is a tap away.
    @Published var showOnlyMyMatchups = true

    @Published private(set) var isTrackingLiveActivity = LiveActivityController.shared.isTracking

    private let loader = ScoresLoader()
    private let service = BestBallService()
    private let liveActivities = LiveActivityController.shared
    private var account: SleeperAccount?
    private var hasStarted = false

    /// Set when the user turns the Live Activities off so refreshes don't bring
    /// them back until they ask for them again.
    static let liveActivityMutedKey = "bestball.liveActivityMuted"

    static let weeks = 1...18

    var currentSeason: Int {
        state.flatMap { Int($0.leagueSeason) } ?? Calendar.current.component(.year, from: Date())
    }

    var trackedLeagueCount: Int { liveActivities.trackedLeagueIDs.count }

    /// Leagues that actually have something to show this week.
    var visibleLeagues: [LeagueWeek] {
        leagueWeeks.filter { !matchups(in: $0).isEmpty }
    }

    func matchups(in leagueWeek: LeagueWeek) -> [MatchupScore] {
        guard showOnlyMyMatchups, leagueWeek.userRosterID != nil else {
            return leagueWeek.matchups
        }
        let mine = leagueWeek.matchups.filter { $0.contains(rosterID: leagueWeek.userRosterID) }
        return mine.isEmpty ? leagueWeek.matchups : mine
    }

    // MARK: Lifecycle

    func start() async {
        guard !hasStarted else { return }
        hasStarted = true
        state = try? await service.sportState()

        guard let saved = SharedStore.loadUsername() else {
            username = SharedStore.loadConfig()?.username ?? ""
            return
        }
        username = saved
        isConnected = true
        // Come back to the week the Live Activities are showing rather than
        // jumping to Sleeper's current week.
        await loadAll(week: SharedStore.loadTrackedWeek() ?? state?.defaultWeek ?? 1)
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

        username = name
        SharedStore.saveUsername(name)
        isConnected = true
        await loadAll(week: state?.defaultWeek ?? SharedStore.loadTrackedWeek() ?? 1)

        if let error = errorMessage, leagueWeeks.isEmpty {
            // Connecting failed outright: stay on setup so the user can fix the name.
            SharedStore.clearUsername()
            isConnected = false
            setupError = error
            errorMessage = nil
        }
    }

    func signOut() {
        SharedStore.clearUsername()
        SharedStore.clearConfig()
        username = ""
        account = nil
        leagues = []
        leagueWeeks = []
        errorMessage = nil
        isConnected = false
        isTrackingLiveActivity = false
        BackgroundRefresh.cancel()
        Task { await liveActivities.end() }
    }

    // MARK: Live Activities

    /// Starts or stops tracking for every league at once.
    func toggleLiveActivity() async {
        if liveActivities.isTracking {
            await liveActivities.end()
            UserDefaults.standard.set(true, forKey: Self.liveActivityMutedKey)
            isTrackingLiveActivity = false
        } else {
            UserDefaults.standard.set(false, forKey: Self.liveActivityMutedKey)
            await syncLiveActivities(from: leagueWeeks)
            BackgroundRefresh.schedule()
        }
    }

    /// One Live Activity per league, all tracking the week on screen.
    private func syncLiveActivities(from loaded: [LeagueWeek]) async {
        guard !UserDefaults.standard.bool(forKey: Self.liveActivityMutedKey) else { return }
        guard !loaded.isEmpty else { return }

        let matchups = loaded.prefix(LiveActivityController.maxActivities).compactMap { week in
            week.widgetSnapshot().map {
                LiveActivityController.TrackedMatchup(
                    leagueID: week.leagueID,
                    leagueName: week.leagueName,
                    snapshot: $0
                )
            }
        }
        guard !matchups.isEmpty else { return }

        SharedStore.saveTrackedWeek(loaded[0].week)
        await liveActivities.sync(matchups)
        isTrackingLiveActivity = liveActivities.isTracking
    }

    // MARK: Weeks

    /// Loads every league you're in for one week, then syncs the Live Activities
    /// from the same results instead of fetching twice.
    func loadAll(week targetWeek: Int) async {
        guard isConnected, !username.isEmpty else { return }
        week = min(max(targetWeek, Self.weeks.lowerBound), Self.weeks.upperBound)
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let slice = try await loader.load(username: username, season: currentSeason, week: week)
            state = slice.state ?? state
            account = slice.account
            leagues = slice.leagues
            leagueWeeks = slice.weeks
            if slice.weeks.isEmpty {
                errorMessage = "Couldn't load week \(week) from Sleeper."
            }
        } catch {
            errorMessage = message(for: error)
            return
        }

        // The widget only has room for one league, so it keeps the first one.
        if let snapshot = leagueWeeks.first?.widgetSnapshot() {
            SharedStore.saveSnapshot(snapshot)
            #if canImport(WidgetKit)
            WidgetCenter.shared.reloadAllTimelines()
            #endif
        }

        await syncLiveActivities(from: leagueWeeks)
        if isTrackingLiveActivity { BackgroundRefresh.schedule() }
    }

    func refresh() async {
        await loadAll(week: week)
    }

    func showPreviousWeek() async {
        await loadAll(week: week - 1)
    }

    func showNextWeek() async {
        await loadAll(week: week + 1)
    }

    // MARK: Helpers

    func didEnterBackground() {
        BackgroundRefresh.schedule()
    }

    private func message(for error: Error) -> String {
        if let localized = error as? LocalizedError, let description = localized.errorDescription {
            return description
        }
        return error.localizedDescription
    }
}
