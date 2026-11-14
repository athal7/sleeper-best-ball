import Foundation

public enum BestBallAPIError: LocalizedError {
    case invalidURL(String)
    case httpStatus(Int, URL)
    case decoding(Error, URL)
    case unknownUser(String)

    public var errorDescription: String? {
        switch self {
        case .invalidURL(let path):
            return "Could not build a request for \(path)."
        case .httpStatus(let code, let url):
            return "Sleeper returned HTTP \(code) for \(url.lastPathComponent)."
        case .decoding(_, let url):
            return "Could not read the response from \(url.host ?? "the API")."
        case .unknownUser(let username):
            return "Could not find Sleeper user '\(username)'."
        }
    }
}

/// Thin async client for the public Sleeper API and the ESPN scoreboard feed
/// used for live game clocks.
public actor SleeperAPI {
    public static let shared = SleeperAPI()

    private let session: URLSession
    private let baseURL = "https://api.sleeper.app/v1/"
    private let decoder = JSONDecoder()

    public init(session: URLSession = .shared) {
        self.session = session
    }

    // MARK: Account and leagues

    public func state() async throws -> SportState {
        try await get("state/nfl")
    }

    public func account(username: String) async throws -> SleeperAccount {
        let trimmed = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw BestBallAPIError.unknownUser(username) }
        let encoded = trimmed.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? trimmed
        do {
            return try await get("user/\(encoded)")
        } catch BestBallAPIError.httpStatus(let code, _) where code == 404 {
            throw BestBallAPIError.unknownUser(trimmed)
        }
    }

    public func leagues(userID: String, season: Int) async throws -> [LeagueSummary] {
        try await get("user/\(userID)/leagues/nfl/\(season)")
    }

    public func league(id: String) async throws -> SleeperLeague {
        try await get("league/\(id)")
    }

    public func rosters(leagueID: String) async throws -> [SleeperRoster] {
        try await get("league/\(leagueID)/rosters")
    }

    public func users(leagueID: String) async throws -> [SleeperAccount] {
        try await get("league/\(leagueID)/users")
    }

    public func matchups(leagueID: String, week: Int) async throws -> [SleeperMatchup] {
        try await get("league/\(leagueID)/matchups/\(week)")
    }

    public func winnersBracket(leagueID: String) async throws -> [SleeperBracketGame] {
        try await get("league/\(leagueID)/winners_bracket")
    }

    public func losersBracket(leagueID: String) async throws -> [SleeperBracketGame] {
        try await get("league/\(leagueID)/losers_bracket")
    }

    // MARK: Weekly data

    public func stats(season: Int, week: Int) async throws -> StatTable {
        let lines: [String: StatLine] = try await get("stats/nfl/regular/\(season)/\(week)")
        return Scoring.table(from: lines)
    }

    public func projections(season: Int, week: Int) async throws -> StatTable {
        let lines: [String: StatLine] = try await get("projections/nfl/regular/\(season)/\(week)")
        return Scoring.table(from: lines)
    }

    /// Full player directory, cached on disk so widget refreshes don't keep
    /// downloading Sleeper's ~10 MB file.
    public func players(maxAge: TimeInterval = 24 * 60 * 60) async throws -> [String: SleeperPlayer] {
        if let cached = SharedStore.loadPlayers(maxAge: maxAge) {
            return cached
        }
        let data = try await fetch(path: "players/nfl", timeout: 90)
        let directory = try SleeperPlayer.decodeDirectory(from: data)
        SharedStore.savePlayers(directory)
        return directory
    }

    // MARK: Live games (ESPN)

    public func games(season: Int, week: Int) async throws -> [String: TeamGame] {
        var components = URLComponents(string: "https://partners.api.espn.com/v2/sports/football/nfl/events")!
        components.queryItems = [
            URLQueryItem(name: "limit", value: "50"),
            URLQueryItem(name: "season", value: String(season)),
            URLQueryItem(name: "week", value: String(week)),
        ]
        guard let url = components.url else {
            throw BestBallAPIError.invalidURL("ESPN events")
        }
        let data = try await fetch(url: url, timeout: 30)
        let scoreboard: ESPNScoreboard
        do {
            scoreboard = try decoder.decode(ESPNScoreboard.self, from: data)
        } catch {
            throw BestBallAPIError.decoding(error, url)
        }

        var games: [String: TeamGame] = [:]
        for event in scoreboard.events {
            for competition in event.competitions {
                let competitors = competition.competitors
                guard competitors.count >= 2 else { continue }
                let quarter = competition.status.period ?? 0
                let clock = competition.status.clock ?? 0
                let statusText = competition.status.type.shortDetail
                    ?? competition.status.type.detail
                    ?? ""
                let kickoff = Self.parseDate(competition.date)
                    ?? Self.parseDate(competition.time?.value)

                for competitor in competitors {
                    guard let opponent = competitors.first(where: {
                        $0.team.abbreviation != competitor.team.abbreviation
                    }) else { continue }
                    let team = Self.normalize(competitor.team.abbreviation)
                    games[team] = TeamGame(
                        team: team,
                        opponent: Self.normalize(opponent.team.abbreviation),
                        quarter: quarter,
                        clock: clock,
                        statusText: statusText,
                        isHome: competitor.homeAway == "home",
                        score: competitor.score?.value,
                        opponentScore: opponent.score?.value,
                        kickoff: kickoff
                    )
                }
            }
        }
        return games
    }

    static func normalize(_ abbreviation: String) -> String {
        abbreviation == "WSH" ? "WAS" : abbreviation
    }

    static func parseDate(_ string: String?) -> Date? {
        guard let string, !string.isEmpty else { return nil }
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: string) { return date }
        let standard = ISO8601DateFormatter()
        if let date = standard.date(from: string) { return date }
        let fallback = DateFormatter()
        fallback.locale = Locale(identifier: "en_US_POSIX")
        fallback.timeZone = TimeZone(identifier: "UTC")
        fallback.dateFormat = "yyyy-MM-dd'T'HH:mmZ"
        return fallback.date(from: string)
    }

    // MARK: Transport

    private func get<T: Decodable>(_ path: String) async throws -> T {
        let data = try await fetch(path: path)
        guard let url = URL(string: baseURL + path) else {
            throw BestBallAPIError.invalidURL(path)
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw BestBallAPIError.decoding(error, url)
        }
    }

    private func fetch(path: String, timeout: TimeInterval = 30) async throws -> Data {
        guard let url = URL(string: baseURL + path) else {
            throw BestBallAPIError.invalidURL(path)
        }
        return try await fetch(url: url, timeout: timeout)
    }

    private func fetch(url: URL, timeout: TimeInterval) async throws -> Data {
        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw BestBallAPIError.httpStatus(0, url)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw BestBallAPIError.httpStatus(http.statusCode, url)
        }
        return data
    }
}

// MARK: - ESPN scoreboard payloads

private struct ESPNScoreboard: Decodable {
    let events: [ESPNEvent]
}

private struct ESPNEvent: Decodable {
    let competitions: [ESPNCompetition]
}

private struct ESPNCompetition: Decodable {
    let date: String?
    let time: ESPNGameTime?
    let competitors: [ESPNCompetitor]
    let status: ESPNStatus
}

private struct ESPNGameTime: Decodable {
    let value: String?
}

private struct ESPNCompetitor: Decodable {
    let homeAway: String?
    let team: ESPNTeam
    let score: ESPNScore?
}

private struct ESPNTeam: Decodable {
    let abbreviation: String
}

private struct ESPNScore: Decodable {
    let value: Double?
}

private struct ESPNStatus: Decodable {
    let period: Int?
    let clock: Double?
    let type: ESPNStatusType
}

private struct ESPNStatusType: Decodable {
    let detail: String?
    let shortDetail: String?
}
