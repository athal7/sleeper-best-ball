import Foundation

// MARK: - Sleeper API payloads

public struct SportState: Decodable, Sendable {
    public let week: Int
    public let season: String
    public let seasonType: String
    public let leagueSeason: String
    public let displayWeek: Int

    public init(week: Int, season: String, seasonType: String, leagueSeason: String, displayWeek: Int) {
        self.week = week
        self.season = season
        self.seasonType = seasonType
        self.leagueSeason = leagueSeason
        self.displayWeek = displayWeek
    }

    enum CodingKeys: String, CodingKey {
        case week, season
        case seasonType = "season_type"
        case leagueSeason = "league_season"
        case displayWeek = "display_week"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        week = (try? container.decode(Int.self, forKey: .week)) ?? 0
        season = (try? container.decode(String.self, forKey: .season)) ?? ""
        seasonType = (try? container.decode(String.self, forKey: .seasonType)) ?? "regular"
        displayWeek = (try? container.decode(Int.self, forKey: .displayWeek)) ?? week
        leagueSeason = (try? container.decode(String.self, forKey: .leagueSeason)) ?? season
    }

    /// The week the app should open on, mirroring the Streamlit app's Context.
    public var defaultWeek: Int {
        (seasonType == "regular" && displayWeek > 0) ? displayWeek : 1
    }
}

public struct SleeperAccount: Decodable, Identifiable, Hashable, Sendable {
    public let userID: String
    public let username: String?
    public let displayName: String?
    public let avatar: String?

    public var id: String { userID }

    public init(userID: String, username: String?, displayName: String?, avatar: String? = nil) {
        self.userID = userID
        self.username = username
        self.displayName = displayName
        self.avatar = avatar
    }

    enum CodingKeys: String, CodingKey {
        case userID = "user_id"
        case username
        case displayName = "display_name"
        case avatar
    }
}

public struct LeagueSummary: Decodable, Identifiable, Hashable, Sendable {
    public let leagueID: String
    public let name: String
    public let season: String
    public let status: String
    public let totalRosters: Int?
    public let avatar: String?

    public var id: String { leagueID }

    public init(leagueID: String, name: String, season: String, status: String,
                totalRosters: Int? = nil, avatar: String? = nil) {
        self.leagueID = leagueID
        self.name = name
        self.season = season
        self.status = status
        self.totalRosters = totalRosters
        self.avatar = avatar
    }

    enum CodingKeys: String, CodingKey {
        case leagueID = "league_id"
        case name, season, status, avatar
        case totalRosters = "total_rosters"
    }

    /// Sleeper has shipped league IDs as both strings and numbers over the years.
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        leagueID = try container.decodeLossyID(forKey: .leagueID)
        name = (try? container.decode(String.self, forKey: .name)) ?? "League"
        season = (try? container.decodeFlexibleString(forKey: .season)) ?? ""
        status = (try? container.decode(String.self, forKey: .status)) ?? ""
        totalRosters = try? container.decode(Int.self, forKey: .totalRosters)
        avatar = try? container.decode(String.self, forKey: .avatar)
    }
}

public struct SleeperLeague: Decodable, Sendable {
    public let name: String
    public let season: String
    public let status: String
    public let scoringSettings: [String: Double]
    public let rosterPositions: [String]
    public let settings: Settings

    public struct Settings: Decodable, Sendable {
        public let playoffWeekStart: Int?
        public let playoffTeams: Int?
        public let playoffRoundType: Int?
        public let numTeams: Int?
        /// 1 for best-ball leagues, which don't allow adds, drops, or trades.
        public let bestBall: Int?

        enum CodingKeys: String, CodingKey {
            case playoffWeekStart = "playoff_week_start"
            case playoffTeams = "playoff_teams"
            case playoffRoundType = "playoff_round_type"
            case numTeams = "num_teams"
            case bestBall = "best_ball"
        }
    }

    enum CodingKeys: String, CodingKey {
        case name, season, status, settings
        case scoringSettings = "scoring_settings"
        case rosterPositions = "roster_positions"
    }

    public init(name: String, season: String, status: String, scoringSettings: [String: Double],
                rosterPositions: [String], settings: Settings) {
        self.name = name
        self.season = season
        self.status = status
        self.scoringSettings = scoringSettings
        self.rosterPositions = rosterPositions
        self.settings = settings
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = (try? container.decode(String.self, forKey: .name)) ?? "League"
        season = (try? container.decodeFlexibleString(forKey: .season)) ?? ""
        status = (try? container.decode(String.self, forKey: .status)) ?? ""
        scoringSettings = (try? container.decode([String: Double].self, forKey: .scoringSettings)) ?? [:]
        rosterPositions = (try? container.decode([String].self, forKey: .rosterPositions)) ?? []
        settings = (try? container.decode(Settings.self, forKey: .settings))
            ?? Settings(playoffWeekStart: nil, playoffTeams: nil, playoffRoundType: nil,
                        numTeams: nil, bestBall: nil)
    }
}

public struct SleeperRoster: Decodable, Identifiable, Sendable {
    public let rosterID: Int
    public let ownerID: String?
    public let players: [String]
    public let wins: Double
    public let losses: Double
    public let fpts: Double
    public let teamName: String?

    public var id: Int { rosterID }

    public init(rosterID: Int, ownerID: String?, players: [String],
                wins: Double, losses: Double, fpts: Double, teamName: String?) {
        self.rosterID = rosterID
        self.ownerID = ownerID
        self.players = players
        self.wins = wins
        self.losses = losses
        self.fpts = fpts
        self.teamName = teamName
    }

    enum CodingKeys: String, CodingKey {
        case rosterID = "roster_id"
        case ownerID = "owner_id"
        case players, settings, metadata
    }

    private struct Settings: Decodable {
        let wins: Double?
        let losses: Double?
        let fpts: Double?
    }

    private struct Metadata: Decodable {
        let teamName: String?

        enum CodingKeys: String, CodingKey {
            case teamName = "team_name"
        }
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        rosterID = try container.decode(Int.self, forKey: .rosterID)
        ownerID = try? container.decode(String.self, forKey: .ownerID)
        players = (try? container.decode([String].self, forKey: .players)) ?? []
        let settings = (try? container.decode(Settings.self, forKey: .settings)) ?? Settings(wins: nil, losses: nil, fpts: nil)
        wins = settings.wins ?? 0
        losses = settings.losses ?? 0
        fpts = settings.fpts ?? 0
        teamName = (try? container.decode(Metadata.self, forKey: .metadata))?.teamName
    }
}

public struct SleeperMatchup: Decodable, Sendable {
    public let rosterID: Int
    public let matchupID: Int?
    public let players: [String]?

    public init(rosterID: Int, matchupID: Int?, players: [String]? = nil) {
        self.rosterID = rosterID
        self.matchupID = matchupID
        self.players = players
    }

    enum CodingKeys: String, CodingKey {
        case rosterID = "roster_id"
        case matchupID = "matchup_id"
        case players
    }
}

public struct SleeperBracketGame: Decodable, Sendable {
    public let round: Int?
    public let team1: Int?
    public let team2: Int?

    public init(round: Int?, team1: Int?, team2: Int?) {
        self.round = round
        self.team1 = team1
        self.team2 = team2
    }

    enum CodingKeys: String, CodingKey {
        case round = "r"
        case team1 = "t1"
        case team2 = "t2"
    }
}

// MARK: - Players

public struct SleeperPlayer: Codable, Identifiable, Hashable, Sendable {
    public let playerID: String
    public let firstName: String
    public let lastName: String
    public let position: String
    public let team: String
    public let injuryStatus: String?

    public var id: String { playerID }

    public init(playerID: String, firstName: String, lastName: String, position: String,
                team: String, injuryStatus: String?) {
        self.playerID = playerID
        self.firstName = firstName
        self.lastName = lastName
        self.position = position
        self.team = team
        self.injuryStatus = injuryStatus
    }

    /// Mirror of the Streamlit app's `Player.name`: first initial plus last name.
    public var displayName: String {
        guard !firstName.isEmpty, !lastName.isEmpty else {
            return lastName.isEmpty ? firstName : lastName
        }
        return "\(firstName.prefix(1)). \(lastName)"
    }

    private struct RawPlayer: Decodable {
        let first_name: String?
        let last_name: String?
        let position: String?
        let team: String?
        let injury_status: String?
    }

    /// Slims the ~10 MB `/players/nfl` payload down to the fields this app uses.
    public static func decodeDirectory(from data: Data) throws -> [String: SleeperPlayer] {
        let raw = try JSONDecoder().decode([String: RawPlayer].self, from: data)
        var directory: [String: SleeperPlayer] = [:]
        directory.reserveCapacity(raw.count)
        for (id, player) in raw {
            guard let position = player.position, !position.isEmpty else { continue }
            directory[id] = SleeperPlayer(
                playerID: id,
                firstName: player.first_name ?? "",
                lastName: player.last_name ?? "",
                position: position,
                team: player.team ?? "",
                injuryStatus: player.injury_status.flatMap { $0.isEmpty ? nil : $0 }
            )
        }
        return directory
    }
}

// MARK: - Stat lines

/// One player's stat row. Sleeper mixes numbers with strings and nulls, so
/// decoding keeps only numeric values and ignores everything else.
public struct StatLine: Decodable, Sendable {
    public let values: [String: Double]

    public init(values: [String: Double]) {
        self.values = values
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: AnyCodingKey.self)
        var values: [String: Double] = [:]
        values.reserveCapacity(container.allKeys.count)
        for key in container.allKeys {
            if let value = try? container.decode(Double.self, forKey: key) {
                values[key.stringValue] = value
            }
        }
        self.values = values
    }
}

public typealias StatTable = [String: [String: Double]]

/// League scoring multiplied against a stat line, exactly like
/// `League._calc_points_from_stats` in the Streamlit app.
public enum Scoring {
    public static func points(stats: [String: Double], scoring: [String: Double]) -> Double {
        var total = 0.0
        for (stat, weight) in scoring {
            if let value = stats[stat] {
                total += value * weight
            }
        }
        return total
    }

    public static func table(from lines: [String: StatLine]) -> StatTable {
        lines.mapValues(\.values)
    }
}

// MARK: - Live game status (ESPN)

public struct TeamGame: Hashable, Sendable {
    public let team: String
    public let opponent: String
    public let quarter: Int
    public let clock: Double
    public let statusText: String
    public let isHome: Bool
    public let score: Double?
    public let opponentScore: Double?
    public let kickoff: Date?

    public init(team: String, opponent: String, quarter: Int, clock: Double,
                statusText: String, isHome: Bool, score: Double?,
                opponentScore: Double?, kickoff: Date?) {
        self.team = team
        self.opponent = opponent
        self.quarter = quarter
        self.clock = clock
        self.statusText = statusText
        self.isHome = isHome
        self.score = score
        self.opponentScore = opponentScore
        self.kickoff = kickoff
    }

    /// Fraction of the game elapsed, the same formula the Streamlit app derives
    /// from the ESPN quarter and clock.
    public var pctPlayed: Double {
        let raw = (Double(quarter) * 15 - clock / 60) / 60
        return min(max(raw, 0), 1)
    }
}

// MARK: - Decoding helpers

struct AnyCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int?

    init(stringValue: String) {
        self.stringValue = stringValue
        self.intValue = nil
    }

    init?(intValue: Int) {
        self.stringValue = String(intValue)
        self.intValue = intValue
    }
}

private extension KeyedDecodingContainer {
    func decodeLossyID(forKey key: Key) throws -> String {
        if let value = try? decode(String.self, forKey: key) {
            return value
        }
        if let value = try? decode(Int64.self, forKey: key) {
            return String(value)
        }
        throw DecodingError.dataCorruptedError(
            forKey: key, in: self, debugDescription: "Expected a string or integer id"
        )
    }

    func decodeFlexibleString(forKey key: Key) throws -> String {
        if let value = try? decode(String.self, forKey: key) {
            return value
        }
        if let value = try? decode(Int.self, forKey: key) {
            return String(value)
        }
        throw DecodingError.dataCorruptedError(
            forKey: key, in: self, debugDescription: "Expected a string or integer"
        )
    }
}
