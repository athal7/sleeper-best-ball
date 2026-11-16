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

    /// The matchups screen starts on your own game; the full slate is a tap away.
    @Published var showOnlyMyMatchups = true

    @Published private(set) var isTrackingLiveActivity = LiveActivityController.shared.isTracking

    private let service = BestBallService()
    private let liveActivities = LiveActivityController.shared
    private var account: SleeperAccount?
    private var snapshot: WidgetSnapshot?
    private var hasStarted = false

    /// Set when the user dismisses the Live Activities so refreshes don't bring
    /// them back until they ask for them again.
    private static let liveActivityMutedKey = "bestball.liveActivityMuted"

    static let weeks = 1...18

    var isConnected: Bool { config != nil }
    var currentSeason: Int {
        state.flatMap { Int($0.leagueSeason) } ?? Calendar.current.component(.year, from: Date())
    }

    /// Your matchup first when the filter is on, otherwise the whole week.
    var visibleMatchups: [MatchupScore] {
        guard let week else { return [] }
        guard showOnlyMyMatchups, week.userRosterID != nil else { return week.matchups }
        let mine = week.matchups.filter { $0.contains(rosterID: week.userRosterID) }
        return mine.isEmpty ? week.matchups : mine
    }

    // MARK: Lifecycle

    func start() async {
        guard !hasStarted else { return }
        hasStarted = true
        config = SharedStore.loadConfig()
        username = SharedStore.loadUsername() ?? config?.username ?? ""
        state = try? await service.sportState()
        if let config {
            await load(week: config.week)
        }
        // The account is remembered independently of the league, so the league
        // picker is ready without retyping the username.
        if !username.isEmpty {
            try? await fetchAccount(username: username)
        }
        await refreshLiveActivities()
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
            if leagues.isEmpty {
                setupError = "No \(currentSeason) NFL leagues found for that account."
            }
            await refreshLiveActivities()
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
        SharedStore.saveUsername(config.username)
        await load(week: config.week)
        await refreshLiveActivities()
    }

    /// Leaves the league but keeps the account, so picking another one doesn't
    /// mean retyping your username. Live Activities for your other leagues keep
    /// running.
    func signOut() {
        SharedStore.clearConfig()
        config = nil
        week = nil
        errorMessage = nil
        snapshot = nil
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
            await refreshLiveActivities()
        }
    }

    /// One Live Activity per in-season league, all tracking the current week.
    func refreshLiveActivities() async {
        guard !UserDefaults.standard.bool(forKey: Self.liveActivityMutedKey) else { return }
        guard !username.isEmpty else { return }

        if account == nil || leagues.isEmpty {
            try? await fetchAccount(username: username)
        }
        guard let account else { return }

        let currentWeek = state?.defaultWeek ?? 1
        let userID = account.userID
        let plans = leagues
            .filter { $0.status == "in_season" }
            .prefix(LiveActivityController.maxActivities)
            .map { (id: $0.leagueID, name: $0.name) }
        guard !plans.isEmpty else {
            await liveActivities.end()
            isTrackingLiveActivity = false
            return
        }

        let service = self.service
        let matchups = await withTaskGroup(
            of: LiveActivityController.TrackedMatchup?.self
        ) { group in
            for plan in plans {
                group.addTask {
                    guard let loaded = try? await service.loadWeek(
                        leagueID: plan.id,
                        week: currentWeek,
                        userID: userID
                    ), let snapshot = loaded.widgetSnapshot() else {
                        return nil
                    }
                    return LiveActivityController.TrackedMatchup(
                        leagueID: plan.id,
                        leagueName: plan.name,
                        snapshot: snapshot
                    )
                }
            }
            var results: [LiveActivityController.TrackedMatchup] = []
            for await result in group {
                if let result { results.append(result) }
            }
            return results
        }

        await liveActivities.sync(matchups)
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
            }
        } catch {
            errorMessage = message(for: error)
        }
    }

    func refresh() async {
        await load(week: week?.week ?? config?.week ?? 1)
        await refreshLiveActivities()
    }

    func showPreviousWeek() async {
        await load(week: (week?.week ?? config?.week ?? 1) - 1)
    }

    func showNextWeek() async {
        await load(week: (week?.week ?? config?.week ?? 1) + 1)
    }

    // MARK: Helpers

    private func fetchAccount(username name: String) async throws {
        if state == nil { state = try await service.sportState() }
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
