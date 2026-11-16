import Foundation

// MARK: - Scores

public struct TeamScore: Identifiable, Hashable, Sendable {
    public let rosterID: Int
    public let name: String
    public let username: String
    public let avatar: String?
    public let record: String
    public let rank: Int
    public let points: Double
    public let projected: Double
    public let players: [RosterPlayer]

    public var id: Int { rosterID }

    public var avatarURL: URL? {
        guard let avatar, !avatar.isEmpty else { return nil }
        return URL(string: "https://sleepercdn.com/avatars/thumbs/\(avatar)")
    }

    /// "2 done / 3 live / 4 left", counting only players with a projection.
    public var playedCounts: String {
        let active = players.filter { $0.projection > 0 }
        let done = active.filter(\.isFinal).count
        let live = active.filter(\.isLive).count
        let left = active.filter { $0.pctPlayed == 0 }.count
        return "\(done) done / \(live) live / \(left) left"
    }

    public init(rosterID: Int, name: String, username: String, avatar: String?,
                record: String, rank: Int, points: Double, projected: Double,
                players: [RosterPlayer]) {
        self.rosterID = rosterID
        self.name = name
        self.username = username
        self.avatar = avatar
        self.record = record
        self.rank = rank
        self.points = points
        self.projected = projected
        self.players = players
    }

    public func player(inSlot slot: String) -> RosterPlayer? {
        players.first { $0.slot == slot }
    }
}

public struct MatchupScore: Identifiable, Hashable, Sendable {
    public let matchupID: Int
    public let teams: [TeamScore]

    public var id: Int { matchupID }

    public init(matchupID: Int, teams: [TeamScore]) {
        self.matchupID = matchupID
        self.teams = teams
    }

    public func contains(rosterID: Int?) -> Bool {
        guard let rosterID else { return false }
        return teams.contains { $0.rosterID == rosterID }
    }
}

public struct LeagueWeek: Hashable, Sendable {
    public let leagueID: String
    public let leagueName: String
    public let week: Int
    public let season: Int
    public let matchups: [MatchupScore]
    public let userRosterID: Int?
    public let updated: Date

    public init(leagueID: String, leagueName: String, week: Int, season: Int,
                matchups: [MatchupScore], userRosterID: Int?, updated: Date) {
        self.leagueID = leagueID
        self.leagueName = leagueName
        self.week = week
        self.season = season
        self.matchups = matchups
        self.userRosterID = userRosterID
        self.updated = updated
    }

    public var userTeam: TeamScore? {
        matchups.flatMap(\.teams).first { $0.rosterID == userRosterID }
    }

    public func matchup(containing rosterID: Int?) -> MatchupScore? {
        matchups.first { $0.contains(rosterID: rosterID) }
    }

    /// The compact summary the widget renders.
    public func widgetSnapshot() -> WidgetSnapshot? {
        guard let team = userTeam ?? matchups.first?.teams.first else { return nil }
        let opponent = matchup(containing: team.rosterID)?.teams.first { $0.rosterID != team.rosterID }
        return WidgetSnapshot(
            leagueName: leagueName,
            week: week,
            teamName: team.name,
            record: team.record,
            rank: team.rank,
            projected: team.projected,
            points: team.points,
            opponentName: opponent?.name,
            opponentProjected: opponent?.projected,
            opponentPoints: opponent?.points,
            updated: updated
        )
    }
}

// MARK: - Service

public struct BestBallService: Sendable {
    private let api: SleeperAPI

    public init(api: SleeperAPI = .shared) {
        self.api = api
    }

    /// Resolves a Sleeper username to its account and this season's leagues.
    public func lookup(username: String, season: Int) async throws
        -> (account: SleeperAccount, leagues: [LeagueSummary]) {
        let account = try await api.account(username: username)
        let leagues = try await api.leagues(userID: account.userID, season: season)
        return (account, leagues)
    }

    public func sportState() async throws -> SportState {
        try await api.state()
    }

    /// Loads and scores one league week: rosters, best-ball lineups, live
    /// game clocks, and matchup pairings.
    public func loadWeek(leagueID: String, week: Int, userID: String? = nil) async throws -> LeagueWeek {
        let league = try await api.league(id: leagueID)
        let season = Int(league.season) ?? Calendar.current.component(.year, from: Date())

        async let rostersRequest = api.rosters(leagueID: leagueID)
        async let usersRequest = api.users(leagueID: leagueID)
        async let playersRequest = api.players()
        async let statsRequest = api.stats(season: season, week: week)
        async let projectionsRequest = api.projections(season: season, week: week)
        async let gamesRequest = api.games(season: season, week: week)

        let rosters = try await rostersRequest
        let users = try await usersRequest
        let directory = try await playersRequest
        let stats = (try? await statsRequest) ?? [:]
        let projections = (try? await projectionsRequest) ?? [:]
        let games = (try? await gamesRequest) ?? [:]

        let playoffWeekStart = league.settings.playoffWeekStart ?? 15
        let pairings: [(matchupID: Int, rosterID: Int)]
        if week >= playoffWeekStart {
            pairings = try await playoffPairings(
                leagueID: leagueID,
                round: week - playoffWeekStart + 1
            )
        } else {
            let matchups = try await api.matchups(leagueID: leagueID, week: week)
            pairings = matchups.compactMap { matchup in
                matchup.matchupID.map { (matchupID: $0, rosterID: matchup.rosterID) }
            }
        }

        let usersByID = Dictionary(
            users.map { ($0.userID, $0) },
            uniquingKeysWith: { first, _ in first }
        )

        // Standings: wins then total points, like Data.get_rosters.
        let rankedRosters = rosters.sorted { lhs, rhs in
            if lhs.wins != rhs.wins { return lhs.wins > rhs.wins }
            if lhs.fpts != rhs.fpts { return lhs.fpts > rhs.fpts }
            return lhs.rosterID < rhs.rosterID
        }
        var ranks: [Int: Int] = [:]
        for (index, roster) in rankedRosters.enumerated() {
            ranks[roster.rosterID] = index + 1
        }

        var teams: [Int: TeamScore] = [:]
        for roster in rosters {
            let user = roster.ownerID.flatMap { usersByID[$0] }
            let username = user?.displayName ?? user?.username ?? ""
            let teamName = roster.teamName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let name = teamName.isEmpty ? "Team \(username)" : teamName

            let players = BestBallEngine.players(
                playerIDs: roster.players,
                directory: directory,
                stats: stats,
                projections: projections,
                scoring: league.scoringSettings,
                games: games,
                gamesAvailable: !games.isEmpty
            )
            let lineup = BestBallEngine.lineup(players, rosterPositions: league.rosterPositions)
            let totals = BestBallEngine.totals(for: lineup)

            teams[roster.rosterID] = TeamScore(
                rosterID: roster.rosterID,
                name: name,
                username: username,
                avatar: user?.avatar,
                record: "\(Int(roster.wins))-\(Int(roster.losses))",
                rank: ranks[roster.rosterID] ?? 0,
                points: totals.points,
                projected: totals.projected,
                players: lineup
            )
        }

        var grouped: [Int: [TeamScore]] = [:]
        for pairing in pairings {
            guard let team = teams[pairing.rosterID] else { continue }
            grouped[pairing.matchupID, default: []].append(team)
        }
        var matchups: [MatchupScore] = grouped
            .filter { $0.value.count == 2 }
            .map { MatchupScore(matchupID: $0.key, teams: $0.value) }
            .sorted { $0.matchupID < $1.matchupID }

        let userRosterID = rosters.first { $0.ownerID == userID }?.rosterID
        if let userRosterID {
            matchups.sort {
                !$0.contains(rosterID: userRosterID) && $1.contains(rosterID: userRosterID)
            }
        }

        return LeagueWeek(
            leagueID: leagueID,
            leagueName: league.name,
            week: week,
            season: season,
            matchups: matchups,
            userRosterID: userRosterID,
            updated: Date()
        )
    }

    /// Playoffs don't always carry a matchup_id in Sleeper's matchups endpoint,
    /// so pair teams from the winners and losers brackets. Mirrors
    /// `Data.get_matchups` in the Streamlit app.
    private func playoffPairings(leagueID: String, round: Int) async throws -> [(matchupID: Int, rosterID: Int)] {
        async let winnersRequest = api.winnersBracket(leagueID: leagueID)
        async let losersRequest = api.losersBracket(leagueID: leagueID)
        let winners = (try? await winnersRequest) ?? []
        let losers = (try? await losersRequest) ?? []

        var pairings: [(matchupID: Int, rosterID: Int)] = []
        var matchupID = 1
        for bracket in [winners, losers] {
            for game in bracket where game.round == round {
                guard let team1 = game.team1, let team2 = game.team2 else { continue }
                pairings.append((matchupID, team1))
                pairings.append((matchupID, team2))
                matchupID += 1
            }
        }
        return pairings
    }
}
