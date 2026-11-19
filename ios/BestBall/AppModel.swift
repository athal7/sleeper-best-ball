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
    /// False until a waiver scan has finished once, so the screen shows
    /// "scoring" instead of claiming there are no adds.
    @Published private(set) var hasScannedWaivers = false

    /// Win-win trade offers across every league, best first.
    @Published private(set) var trades: [TradeOffer] = []
    /// Per-league rosters and projections the Trade Analyzer works from.
    @Published private(set) var tradeBoards: [TradeBoard] = []
    @Published private(set) var isScanningTrades = false
    /// Same guard for the trade list: an unfinished scan is not an empty scan.
    @Published private(set) var hasScannedTrades = false

    private let loader = ScoresLoader()
    private let service = BestBallService()
    private let waiverScanner = WaiverScanner()
    private let tradeScanner = TradeScanner()
    private var lastWaiverScan: Date?
    private let liveActivities = LiveActivityController.shared
    private var account: SleeperAccount?
    private var hasStarted = false
    /// True once you tap a week arrow onto a week that isn't the current one.
    /// From then on the screen stays where you put it; arrowing back to the
    /// current week hands control back to Sleeper.
    private var hasChosenWeek = false

    /// Set when the user turns the Live Activities off. The mute is scoped to the
    /// week it was set in, so next week's kickoff starts tracking again on its
    /// own — the toggle is a veto on this week's games, not a setting.
    static let liveActivityMutedKey = "bestball.liveActivityMuted"
    static let liveActivityMutedWeekKey = "bestball.liveActivityMutedWeek"

    static let weeks = 1...18

    var currentSeason: Int {
        state.flatMap { Int($0.leagueSeason) } ?? Calendar.current.component(.year, from: Date())
    }

    var trackedLeagueCount: Int { liveActivities.trackedLeagueIDs.count }

    /// Sleeper's own week, which moves on by itself once the slate is over.
    private var currentWeek: Int { state?.defaultWeek ?? week }

    /// False when Live Activities are switched off for the app in Settings, which
    /// is the one reason a toggle here cannot do anything.
    var liveActivitiesAuthorized: Bool { liveActivities.isAuthorized }

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
        // Open on whichever is later, the week you were last looking at or
        // Sleeper's current one: a week saved before the rollover is last week's
        // news, while a week you parked on ahead of time is still what you want.
        await loadAll(week: max(SharedStore.loadTrackedWeek() ?? currentWeek, currentWeek))

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
        await loadAll(week: max(SharedStore.loadTrackedWeek() ?? currentWeek, currentWeek))

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
        hasScannedWaivers = false
        hasScannedTrades = false
        trades = []
        tradeBoards = []
        BackgroundRefresh.cancel()
        Task { await liveActivities.end() }
    }

    // MARK: Live Activities

    /// Starts or stops tracking for every league at once.
    func toggleLiveActivity() async {
        if liveActivities.isTracking {
            muteLiveActivity()
            await liveActivities.end()
            isTrackingLiveActivity = false
        } else {
            UserDefaults.standard.removeObject(forKey: Self.liveActivityMutedKey)
            UserDefaults.standard.removeObject(forKey: Self.liveActivityMutedWeekKey)
            await syncLiveActivities(from: leagueWeeks)
            if isTrackingLiveActivity { BackgroundRefresh.schedule() }
        }
    }

    /// One Live Activity per league, all tracking the week on screen.
    ///
    /// This is the only place activities are started or ended, and it runs on
    /// every load, so a game going live turns tracking on by itself and the last
    /// game of the week turns it off again. The toggle only records a veto for the
    /// week on screen.
    private func syncLiveActivities(from loaded: [LeagueWeek]) async {
        guard !loaded.isEmpty else { return }

        let targetWeek = loaded[0].week
        guard !isLiveActivityMuted(for: targetWeek) else {
            isTrackingLiveActivity = liveActivities.isTracking
            return
        }

        // Only leagues with a player on the field right now get an activity, so
        // the Lock Screen isn't holding a card for a league that has nothing
        // live (all games done, or none started yet). The controller ends any
        // card whose league dropped out of this list, so a card never outlives
        // the game that justified it.
        let liveNow = loaded.filter { week in
            week.userTeam?.players.contains(where: \.isLive) == true
        }
        let matchups = liveNow.prefix(LiveActivityController.maxActivities).compactMap { week in
            week.widgetSnapshot().map {
                LiveActivityController.TrackedMatchup(
                    leagueID: week.leagueID,
                    leagueName: week.leagueName,
                    snapshot: $0
                )
            }
        }

        SharedStore.saveTrackedWeek(targetWeek)
        await liveActivities.sync(matchups)
        isTrackingLiveActivity = liveActivities.isTracking
    }

    private func muteLiveActivity() {
        UserDefaults.standard.set(true, forKey: Self.liveActivityMutedKey)
        UserDefaults.standard.set(week, forKey: Self.liveActivityMutedWeekKey)
    }

    /// A mute outlives only the week it was set in: a new week of games is a new
    /// decision, so tracking comes back without the user having to remember.
    private func isLiveActivityMuted(for week: Int) -> Bool {
        guard UserDefaults.standard.bool(forKey: Self.liveActivityMutedKey) else { return false }
        guard UserDefaults.standard.integer(forKey: Self.liveActivityMutedWeekKey) == week else {
            UserDefaults.standard.removeObject(forKey: Self.liveActivityMutedKey)
            UserDefaults.standard.removeObject(forKey: Self.liveActivityMutedWeekKey)
            return false
        }
        return true
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
        hasScannedWaivers = true
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
        hasScannedWaivers = true
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

    // MARK: Trades

    /// Scans every league for win-win offers. The projections are already on
    /// disk from the waiver scan, so this is mostly local lineup scoring.
    func refreshTrades() async {
        guard isConnected, let account, !leagues.isEmpty else { return }
        isScanningTrades = true
        defer { isScanningTrades = false }

        let scan = await tradeScanner.scan(
            leagues: leagues,
            userID: account.userID,
            week: waiverWeek,
            season: currentSeason
        )
        trades = scan.offers
        tradeBoards = scan.boards
        hasScannedTrades = true
    }

    /// The week ends on its own, so refreshing follows it. The state is fetched
    /// first because the decision can't be made with the week saved yesterday.
    func refresh() async {
        if !hasChosenWeek, let latest = try? await service.sportState() {
            state = latest
        }
        await loadAll(week: hasChosenWeek ? week : max(week, currentWeek))
    }

    func showPreviousWeek() async {
        await loadAll(week: week - 1)
        hasChosenWeek = week != currentWeek
    }

    func showNextWeek() async {
        await loadAll(week: week + 1)
        hasChosenWeek = week != currentWeek
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
