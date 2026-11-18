import Combine
import Foundation
import UserNotifications
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

    /// Add/drop suggestions across every league, best first.
    @Published private(set) var waivers: [WaiverPick] = []
    /// Suggestions you haven't opened the Waivers screen for yet.
    @Published private(set) var unseenWaiverCount = 0
    @Published private(set) var isScanningWaivers = false

    private let loader = ScoresLoader()
    private let service = BestBallService()
    private let waiverScanner = WaiverScanner()
    private var lastWaiverScan: Date?
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
        restoreWaivers()

        guard let saved = SharedStore.loadUsername() else {
            username = SharedStore.loadConfig()?.username ?? ""
            return
        }
        username = saved
        isConnected = true
        await WaiverNotifier.requestAuthorization()
        // Come back to the week the Live Activities are showing rather than
        // jumping to Sleeper's current week.
        await loadAll(week: SharedStore.loadTrackedWeek() ?? state?.defaultWeek ?? 1)

        // A remembered name that no longer loads shouldn't strand the user on an
        // empty scores screen: show setup with the name still filled in.
        if leagueWeeks.isEmpty, let error = errorMessage {
            isConnected = false
            setupError = error
            errorMessage = nil
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

        username = name
        SharedStore.saveUsername(name)
        isConnected = true
        await loadAll(week: state?.defaultWeek ?? SharedStore.loadTrackedWeek() ?? 1)

        if let error = errorMessage, leagueWeeks.isEmpty {
            // Connecting failed outright: stay on setup so the user can fix the
            // name. The name itself is kept — retyping it is the annoyance.
            isConnected = false
            setupError = error
            errorMessage = nil
        }
    }

    /// Called as the setup field changes, so the name is remembered as soon as
    /// it's valid and forgotten only once it's actually empty.
    func usernameEdited(_ value: String) {
        let name = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if name.isEmpty {
            SharedStore.clearUsername()
        } else {
            SharedStore.saveUsername(name)
        }
    }

    /// Backs out to the setup screen without forgetting who you are: the username
    /// stays saved and filled in, so coming back is one tap.
    func disconnect() {
        SharedStore.clearConfig()
        account = nil
        leagues = []
        leagueWeeks = []
        errorMessage = nil
        isConnected = false
        isTrackingLiveActivity = false
        waivers = []
        unseenWaiverCount = 0
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

        if needsWaiverScan {
            await refreshWaivers(notify: true)
        }
    }

    // MARK: Waivers

    /// The week waiver values start from: Sleeper's current one, not whichever
    /// week you happen to be browsing.
    var waiverWeek: Int { state?.defaultWeek ?? week }

    /// Recomputed on a half-hour cadence, so pull-to-refresh isn't re-downloading
    /// the rest of the season's projections every time.
    private var needsWaiverScan: Bool {
        guard let lastWaiverScan else { return true }
        if SharedStore.loadWaiverReport()?.week != waiverWeek { return true }
        return Date().timeIntervalSince(lastWaiverScan) > 30 * 60
    }

    private func restoreWaivers() {
        guard let report = SharedStore.loadWaiverReport() else { return }
        waivers = report.picks.filter(\.isUpgrade)
        let seen = SharedStore.seenWaiverIDs()
        unseenWaiverCount = waivers.filter { !seen.contains($0.id) }.count
    }

    func refreshWaivers(notify: Bool) async {
        guard isConnected, let account, !leagues.isEmpty else { return }
        isScanningWaivers = true
        defer { isScanningWaivers = false }

        let targetWeek = waiverWeek
        let picks = await waiverScanner.scan(
            leagues: leagues,
            userID: account.userID,
            week: targetWeek,
            season: currentSeason
        )
        lastWaiverScan = Date()
        waivers = picks
        SharedStore.saveWaiverReport(
            WaiverReport(week: targetWeek, generated: Date(), picks: picks)
        )
        let seen = SharedStore.seenWaiverIDs()
        unseenWaiverCount = picks.filter { !seen.contains($0.id) }.count

        if notify {
            await WaiverNotifier.announce(picks)
        }
    }

    /// Opening the Waivers screen clears the badge and stops repeats about the
    /// same players.
    func markWaiversSeen() {
        SharedStore.markWaiversSeen(waivers.map(\.id))
        unseenWaiverCount = 0
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

/// Local notifications for waiver suggestions. Local (not push) means this works
/// on a free Apple ID, and means the text has to be built when the app wakes up.
enum WaiverNotifier {
    static let threadIdentifier = "bestball.waivers"

    static func requestAuthorization() async {
        let center = UNUserNotificationCenter.current()
        guard await center.notificationSettings().authorizationStatus == .notDetermined else { return }
        _ = try? await center.requestAuthorization(options: [.alert, .sound, .badge])
    }

    /// Announces only picks that have never been announced before, so waking up
    /// hourly with the same three adds stays quiet.
    static func announce(_ picks: [WaiverPick]) async {
        guard !picks.isEmpty else { return }
        let already = SharedStore.notifiedWaiverIDs()
        // Only real upgrades are announced, matching the web guide's filter;
        // reports cached by older builds may still contain filler picks.
        let fresh = picks.filter { $0.isUpgrade && !already.contains($0.id) }
        guard !fresh.isEmpty, let top = fresh.max(by: { $0.uplift < $1.uplift }) else { return }

        let center = UNUserNotificationCenter.current()
        let status = await center.notificationSettings().authorizationStatus
        guard status == .authorized || status == .provisional else { return }

        let content = UNMutableNotificationContent()
        content.title = fresh.count == 1
            ? "Waiver suggestion: \(top.addName)"
            : "\(fresh.count) waiver suggestions"
        content.body = "\(top.leagueName): add \(top.addName) (\(top.addPosition)) for \(top.dropName), +\(String(format: "%.1f", top.uplift)) projected."
        content.sound = .default
        content.threadIdentifier = threadIdentifier

        let request = UNNotificationRequest(
            identifier: "waiver-\(top.id)-\(Int(Date().timeIntervalSince1970))",
            content: content,
            trigger: nil
        )
        guard (try? await center.add(request)) != nil else { return }
        SharedStore.markWaiversNotified(fresh.map(\.id))
    }
}
