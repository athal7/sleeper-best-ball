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

    private let service = BestBallService()
    private let liveActivities = LiveActivityController.shared
    private var account: SleeperAccount?
    private var hasStarted = false

    /// Set when the user dismisses the Live Activities so refreshes don't bring
    /// them back until they ask for them again.
    private static let liveActivityMutedKey = "bestball.liveActivityMuted"

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
        await loadAll(week: state?.defaultWeek ?? 1)
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
            try await fetchAccount(username: name)
            username = name
            SharedStore.saveUsername(name)
            isConnected = true
            await loadAll(week: state?.defaultWeek ?? 1)
        } catch {
            setupError = message(for: error)
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
        }
    }

    /// One Live Activity per league, all tracking the week on screen.
    private func syncLiveActivities(from weeks: [LeagueWeek]) async {
        guard !UserDefaults.standard.bool(forKey: Self.liveActivityMutedKey) else { return }
        guard liveActivities.isAuthorized else {
            isTrackingLiveActivity = false
            return
        }

        let matchups = weeks.prefix(LiveActivityController.maxActivities).compactMap { week in
            week.widgetSnapshot().map {
                LiveActivityController.TrackedMatchup(
                    leagueID: week.leagueID,
                    leagueName: week.leagueName,
                    snapshot: $0
                )
            }
        }
        await liveActivities.sync(matchups)
        isTrackingLiveActivity = liveActivities.isTracking
    }

    // MARK: Weeks

    /// Loads every league you're in for one week, then syncs the Live Activities
    /// from the same results instead of fetching twice.
    func loadAll(week targetWeek: Int) async {
        guard isConnected else { return }
        week = min(max(targetWeek, Self.weeks.lowerBound), Self.weeks.upperBound)
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        if state == nil { state = try? await service.sportState() }

        if account == nil || leagues.isEmpty {
            do {
                try await fetchAccount(username: username)
            } catch {
                errorMessage = message(for: error)
                return
            }
        }

        guard let account else { return }

        let inSeason = leagues.filter { $0.status == "in_season" }
        let plans = (inSeason.isEmpty ? leagues : inSeason)
            .map { (id: $0.leagueID, name: $0.name) }
        guard !plans.isEmpty else {
            leagueWeeks = []
            errorMessage = "No \(currentSeason) NFL leagues found for that account."
            return
        }

        let service = self.service
        let userID = account.userID
        let currentWeek = week
        let loaded = await withTaskGroup(of: (Int, LeagueWeek?).self) { group in
            for (index, plan) in plans.enumerated() {
                group.addTask {
                    let week = try? await service.loadWeek(
                        leagueID: plan.id,
                        week: currentWeek,
                        userID: userID
                    )
                    return (index, week)
                }
            }
            var results: [(Int, LeagueWeek?)] = []
            for await result in group { results.append(result) }
            return results.sorted { $0.0 < $1.0 }.compactMap(\.1)
        }

        leagueWeeks = loaded

        // The widget only has room for one league, so it keeps the first one.
        if let snapshot = loaded.first?.widgetSnapshot() {
            SharedStore.saveSnapshot(snapshot)
            #if canImport(WidgetKit)
            WidgetCenter.shared.reloadAllTimelines()
            #endif
        }

        if loaded.isEmpty {
            errorMessage = "Couldn't load week \(week) from Sleeper."
        }

        await syncLiveActivities(from: loaded)
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

    private func fetchAccount(username name: String) async throws {
        if state == nil { state = try? await service.sportState() }
        let result = try await service.lookup(username: name, season: currentSeason)
        account = result.account
        leagues = result.leagues.sorted(by: Self.leagueOrder)
    }

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
