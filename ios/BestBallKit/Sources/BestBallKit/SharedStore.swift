import Foundation

public enum AppGroup {
    /// Must match the App Group capability on both the app and widget targets.
    /// Both targets write `BBAppGroup` into their Info.plist from the same build
    /// setting, so overriding the bundle identifier keeps the container in sync.
    public static let identifier: String = {
        if let value = Bundle.main.object(forInfoDictionaryKey: "BBAppGroup") as? String,
           !value.isEmpty {
            return value
        }
        return "group.com.sleeperbestball.app"
    }()
}

/// The league this device should show, shared with the widget.
public struct SavedLeague: Codable, Equatable, Sendable {
    public var username: String
    public var userID: String
    public var leagueID: String
    public var leagueName: String
    public var season: Int
    public var week: Int

    public init(username: String, userID: String, leagueID: String,
                leagueName: String, season: Int, week: Int) {
        self.username = username
        self.userID = userID
        self.leagueID = leagueID
        self.leagueName = leagueName
        self.season = season
        self.week = week
    }
}

/// Everything the widget needs, pre-computed so the timeline doesn't have to
/// understand scoring or lineups.
public struct WidgetSnapshot: Codable, Equatable, Sendable {
    public let leagueName: String
    public let week: Int
    public let teamName: String
    public let record: String
    public let rank: Int
    public let projected: Double
    public let points: Double
    public let opponentName: String?
    public let opponentProjected: Double?
    public let opponentPoints: Double?
    public let updated: Date

    public init(leagueName: String, week: Int, teamName: String, record: String,
                rank: Int, projected: Double, points: Double, opponentName: String?,
                opponentProjected: Double?, opponentPoints: Double?, updated: Date) {
        self.leagueName = leagueName
        self.week = week
        self.teamName = teamName
        self.record = record
        self.rank = rank
        self.projected = projected
        self.points = points
        self.opponentName = opponentName
        self.opponentProjected = opponentProjected
        self.opponentPoints = opponentPoints
        self.updated = updated
    }
}

/// App Group backed storage shared by the app and the widget extension.
public enum SharedStore {
    private static let configKey = "bestball.savedLeague"
    private static let accountKey = "bestball.accountUsername"
    private static let snapshotKey = "bestball.widgetSnapshot"
    private static let trackedWeekKey = "bestball.trackedWeek"
    private static let waiverReportKey = "bestball.waiverReport"
    private static let waiversNotifiedKey = "bestball.waiversNotified"
    private static let waiversSeenKey = "bestball.waiversSeen"
    private static let playersFileName = "players.json"
    /// Keeps the remembered ID lists from growing without bound.
    private static let rememberedLimit = 500

    /// Falls back to this process's own defaults when the App Group isn't
    /// available (free Apple ID signing can't use App Groups). The app keeps
    /// working; only the widget loses access to the saved league.
    public static var defaults: UserDefaults {
        guard hasAppGroup,
              let shared = UserDefaults(suiteName: AppGroup.identifier) else {
            return .standard
        }
        return shared
    }

    public static var hasAppGroup: Bool {
        FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: AppGroup.identifier
        ) != nil
    }

    // MARK: Account

    /// The Sleeper username belongs to the account, not to whichever league is
    /// selected, so it outlives `clearConfig()` and users only type it once.
    public static func saveUsername(_ username: String) {
        defaults.set(username, forKey: accountKey)
    }

    public static func loadUsername() -> String? {
        let value = defaults.string(forKey: accountKey)
        return (value?.isEmpty == false) ? value : nil
    }

    public static func clearUsername() {
        defaults.removeObject(forKey: accountKey)
    }

    // MARK: League selection

    public static func saveConfig(_ config: SavedLeague) {
        defaults.set(try? JSONEncoder().encode(config), forKey: configKey)
    }

    public static func loadConfig() -> SavedLeague? {
        guard let data = defaults.data(forKey: configKey) else { return nil }
        return try? JSONDecoder().decode(SavedLeague.self, from: data)
    }

    public static func clearConfig() {
        defaults.removeObject(forKey: configKey)
        defaults.removeObject(forKey: snapshotKey)
    }

    // MARK: Widget snapshot

    public static func saveSnapshot(_ snapshot: WidgetSnapshot) {
        defaults.set(try? JSONEncoder().encode(snapshot), forKey: snapshotKey)
    }

    public static func loadSnapshot() -> WidgetSnapshot? {
        guard let data = defaults.data(forKey: snapshotKey) else { return nil }
        return try? JSONDecoder().decode(WidgetSnapshot.self, from: data)
    }

    // MARK: Live Activity week

    /// Background refresh reloads the week the Live Activities are actually
    /// showing, so it doesn't jump them to another week behind your back.
    public static func saveTrackedWeek(_ week: Int) {
        defaults.set(week, forKey: trackedWeekKey)
    }

    public static func loadTrackedWeek() -> Int? {
        let value = defaults.integer(forKey: trackedWeekKey)
        return value > 0 ? value : nil
    }

    // MARK: Waivers

    public static func saveWaiverReport(_ report: WaiverReport) {
        defaults.set(try? JSONEncoder().encode(report), forKey: waiverReportKey)
    }

    public static func loadWaiverReport() -> WaiverReport? {
        guard let data = defaults.data(forKey: waiverReportKey) else { return nil }
        return try? JSONDecoder().decode(WaiverReport.self, from: data)
    }

    /// Waiver picks already announced in a notification, so a wake-up that finds
    /// the same adds doesn't buzz the phone again.
    public static func notifiedWaiverIDs() -> Set<String> {
        Set(defaults.stringArray(forKey: waiversNotifiedKey) ?? [])
    }

    public static func markWaiversNotified(_ ids: [String]) {
        remember(ids, key: waiversNotifiedKey)
    }

    /// Waiver picks the Waivers screen has shown, so its badge means "new to you".
    public static func seenWaiverIDs() -> Set<String> {
        Set(defaults.stringArray(forKey: waiversSeenKey) ?? [])
    }

    public static func markWaiversSeen(_ ids: [String]) {
        remember(ids, key: waiversSeenKey)
    }

    private static func remember(_ ids: [String], key: String) {
        var list = defaults.stringArray(forKey: key) ?? []
        var known = Set(list)
        for id in ids where known.insert(id).inserted {
            list.append(id)
        }
        if list.count > rememberedLimit {
            list.removeFirst(list.count - rememberedLimit)
        }
        defaults.set(list, forKey: key)
    }

    // MARK: Weekly projections

    public static func loadProjections(season: Int, week: Int, maxAge: TimeInterval) -> StatTable? {
        guard let url = cacheURL(projectionsFileName(season: season, week: week)),
              let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
              let modified = attributes[.modificationDate] as? Date,
              Date().timeIntervalSince(modified) < maxAge,
              let data = try? Data(contentsOf: url) else {
            return nil
        }
        return try? JSONDecoder().decode(StatTable.self, from: data)
    }

    public static func saveProjections(_ table: StatTable, season: Int, week: Int) {
        guard let url = cacheURL(projectionsFileName(season: season, week: week)),
              let data = try? JSONEncoder().encode(table) else { return }
        try? data.write(to: url, options: .atomic)
    }

    private static func projectionsFileName(season: Int, week: Int) -> String {
        "projections-\(season)-\(week).json"
    }

    // MARK: Player directory cache

    public static func loadPlayers(maxAge: TimeInterval) -> [String: SleeperPlayer]? {
        guard let url = cacheURL(playersFileName),
              let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
              let modified = attributes[.modificationDate] as? Date,
              Date().timeIntervalSince(modified) < maxAge,
              let data = try? Data(contentsOf: url) else {
            return nil
        }
        return try? JSONDecoder().decode([String: SleeperPlayer].self, from: data)
    }

    public static func savePlayers(_ players: [String: SleeperPlayer]) {
        guard let url = cacheURL(playersFileName),
              let data = try? JSONEncoder().encode(players) else { return }
        try? data.write(to: url, options: .atomic)
    }

    private static func cacheURL(_ fileName: String) -> URL? {
        let directory: URL?
        if hasAppGroup, let container = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: AppGroup.identifier
        ) {
            directory = container.appendingPathComponent("Caches", isDirectory: true)
        } else {
            directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        }
        guard let directory else { return nil }
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory.appendingPathComponent(fileName)
    }
}
