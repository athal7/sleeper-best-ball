import Foundation

// MARK: - Results

/// One "add X, drop Y" suggestion for a league.
public struct WaiverPick: Codable, Hashable, Identifiable, Sendable {
    public let leagueID: String
    public let leagueName: String
    public let addID: String
    public let addName: String
    public let addPosition: String
    public let addTeam: String
    public let dropID: String
    public let dropName: String
    public let dropPosition: String
    public let dropTeam: String
    /// Projected points gained over the rest of the season, playoff weeks
    /// counted 1.5x. Negative values never make it into a report.
    public let uplift: Double

    /// Stable identity for "have I already been told about this one?".
    public var id: String { "\(leagueID)|\(addID)|\(dropID)" }

    public init(leagueID: String, leagueName: String, addID: String, addName: String,
                addPosition: String, addTeam: String, dropID: String, dropName: String,
                dropPosition: String, dropTeam: String, uplift: Double) {
        self.leagueID = leagueID
        self.leagueName = leagueName
        self.addID = addID
        self.addName = addName
        self.addPosition = addPosition
        self.addTeam = addTeam
        self.dropID = dropID
        self.dropName = dropName
        self.dropPosition = dropPosition
        self.dropTeam = dropTeam
        self.uplift = uplift
    }
}

public struct WaiverReport: Codable, Equatable, Sendable {
    /// The NFL week the projections start from.
    public let week: Int
    public let generated: Date
    public let picks: [WaiverPick]
    /// Leagues where moves are legal and were actually scored.
    public let eligibleLeagues: Int
    /// Best-ball leagues, which have no wire to work: adds, drops and trades are
    /// all disabled by Sleeper.
    public let bestBallLeagues: Int

    public init(week: Int, generated: Date, picks: [WaiverPick],
                eligibleLeagues: Int = 0, bestBallLeagues: Int = 0) {
        self.week = week
        self.generated = generated
        self.picks = picks
        self.eligibleLeagues = eligibleLeagues
        self.bestBallLeagues = bestBallLeagues
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        week = (try? container.decode(Int.self, forKey: .week)) ?? 0
        generated = (try? container.decode(Date.self, forKey: .generated)) ?? Date()
        picks = (try? container.decode([WaiverPick].self, forKey: .picks)) ?? []
        eligibleLeagues = (try? container.decode(Int.self, forKey: .eligibleLeagues)) ?? 0
        bestBallLeagues = (try? container.decode(Int.self, forKey: .bestBallLeagues)) ?? 0
    }
}

/// What one scan found, plus enough context for the screen to explain itself.
public struct WaiverScan: Sendable {
    public let picks: [WaiverPick]
    public let eligibleLeagues: Int
    public let bestBallLeagues: Int

    public init(picks: [WaiverPick], eligibleLeagues: Int, bestBallLeagues: Int) {
        self.picks = picks
        self.eligibleLeagues = eligibleLeagues
        self.bestBallLeagues = bestBallLeagues
    }

    public static let empty = WaiverScan(picks: [], eligibleLeagues: 0, bestBallLeagues: 0)
}

// MARK: - Scanner

/// Ranks free agents by how much they'd improve your best-ball lineup for the
/// rest of the season, simulating an add and a drop for every pairing. A
/// trimmed-down port of `compute_waiver_add_drop_recommendations`.
public struct WaiverScanner: Sendable {
    public struct Options: Sendable {
        /// How many suggestions to keep per league.
        public var picksPerLeague: Int
        /// Free agents to actually simulate, highest rest-of-season total first.
        public var candidateLimit: Int
        /// Suggestions have to be worth at least this many points to be shown.
        public var minUplift: Double

        public init(picksPerLeague: Int = 3, candidateLimit: Int = 25, minUplift: Double = 1) {
            self.picksPerLeague = picksPerLeague
            self.candidateLimit = candidateLimit
            self.minUplift = minUplift
        }
    }

    /// Positions Sleeper projects. Players without one are ignored.
    static let waiverPositions: Set<String> = ["QB", "RB", "WR", "TE", "K", "DEF"]

    private let api: SleeperAPI
    private let options: Options
    private let cacheAge: TimeInterval

    public init(api: SleeperAPI = .shared,
                options: Options = Options(),
                cacheAge: TimeInterval = 6 * 60 * 60) {
        self.api = api
        self.options = options
        self.cacheAge = cacheAge
    }

    /// Scans every league that allows moves, returning the best suggestions
    /// across all of them, best first.
    public func scan(leagues: [LeagueSummary], userID: String, week: Int, season: Int) async -> WaiverScan {
        guard !leagues.isEmpty else { return .empty }

        let details = await withTaskGroup(of: (String, SleeperLeague?).self) { group in
            for league in leagues {
                group.addTask { (league.leagueID, try? await api.league(id: league.leagueID)) }
            }
            var found: [String: SleeperLeague] = [:]
            for await (leagueID, detail) in group {
                if let detail { found[leagueID] = detail }
            }
            return found
        }
        guard !details.isEmpty else { return .empty }

        // Best-ball leagues have no add/drop and no trades, so scoring their wire
        // would only invent moves Sleeper won't let you make.
        let movable = leagues.filter { details[$0.leagueID]?.settings.bestBall != 1 }
        let bestBallLeagues = leagues.count - movable.count
        guard !movable.isEmpty else {
            return WaiverScan(picks: [], eligibleLeagues: 0, bestBallLeagues: bestBallLeagues)
        }

        let endWeek = movable.compactMap { details[$0.leagueID].map { Self.seasonEndWeek($0.settings) } }
            .reduce(18) { min(18, max($0, $1)) }
        let projections = await loadProjections(season: season, weeks: week...max(week, endWeek))
        guard !projections.isEmpty else {
            return WaiverScan(picks: [], eligibleLeagues: movable.count, bestBallLeagues: bestBallLeagues)
        }

        let directory = (try? await api.players()) ?? [:]
        guard !directory.isEmpty else {
            return WaiverScan(picks: [], eligibleLeagues: movable.count, bestBallLeagues: bestBallLeagues)
        }

        let picks = await withTaskGroup(of: [WaiverPick].self) { group in
            for league in movable {
                guard let detail = details[league.leagueID] else { continue }
                group.addTask {
                    await scan(
                        league: league,
                        detail: detail,
                        directory: directory,
                        userID: userID,
                        week: week,
                        projections: projections
                    )
                }
            }
            var picks: [WaiverPick] = []
            for await result in group { picks.append(contentsOf: result) }
            return picks.sorted { $0.uplift > $1.uplift }
        }
        return WaiverScan(picks: picks, eligibleLeagues: movable.count, bestBallLeagues: bestBallLeagues)
    }

    // MARK: One league

    func scan(league: LeagueSummary, detail: SleeperLeague, directory: [String: SleeperPlayer],
              userID: String, week: Int, projections: [Int: StatTable]) async -> [WaiverPick] {
        guard let rosters = try? await api.rosters(leagueID: league.leagueID),
              let myRoster = rosters.first(where: { $0.ownerID == userID })?.players,
              !myRoster.isEmpty else { return [] }

        let slots = LineupSlots.slots(for: detail.rosterPositions)
        guard slots.contains(where: { !$0.isBench }) else { return [] }

        let weeks = (week...max(week, Self.seasonEndWeek(detail.settings))).filter {
            $0 <= 18 && projections[$0] != nil
        }
        guard !weeks.isEmpty else { return [] }

        let scoring = detail.scoringSettings
        func points(_ table: StatTable, _ playerID: String) -> Double {
            guard let stats = table[playerID] else { return 0 }
            return Scoring.points(stats: stats, scoring: scoring)
        }

        var positions: [String: String] = [:]
        for playerID in myRoster {
            if let player = directory[playerID] { positions[playerID] = player.position }
        }
        guard !positions.isEmpty else { return [] }

        let playoffStart = detail.settings.playoffWeekStart ?? 15
        func weight(_ week: Int) -> Double { week >= playoffStart ? 1.5 : 1.0 }

        var weekly: [Int: [String: Double]] = [:]
        for week in weeks {
            let table = projections[week] ?? [:]
            var scored: [String: Double] = [:]
            for playerID in positions.keys { scored[playerID] = points(table, playerID) }
            weekly[week] = scored
        }
        let baseline = weekly.mapValues { lineupTotal($0, positions, slots) }

        // Free agents: everyone with a projection who nobody in this league owns.
        let rostered = Set(rosters.flatMap(\.players))
        var candidates: [(id: String, position: String, weekly: [Int: Double], total: Double)] = []
        for (playerID, player) in directory {
            guard !rostered.contains(playerID), Self.waiverPositions.contains(player.position) else { continue }
            var scored: [Int: Double] = [:]
            var total = 0.0
            for week in weeks {
                let value = points(projections[week] ?? [:], playerID)
                scored[week] = value
                total += value * weight(week)
            }
            guard total > options.minUplift else { continue }
            candidates.append((playerID, player.position, scored, total))
        }
        candidates.sort { $0.total > $1.total }
        candidates = Array(candidates.prefix(options.candidateLimit))
        guard !candidates.isEmpty else { return [] }

        var scored: [(pick: WaiverPick, uplift: Double)] = []
        for dropID in myRoster {
            guard let drop = directory[dropID] else { continue }

            var withoutDrop: [Int: [String: Double]] = [:]
            var withoutDropPositions = positions
            withoutDropPositions.removeValue(forKey: dropID)
            for week in weeks {
                var lineup = weekly[week] ?? [:]
                lineup.removeValue(forKey: dropID)
                withoutDrop[week] = lineup
            }

            for candidate in candidates where candidate.id != dropID {
                var uplift = 0.0
                for week in weeks {
                    var lineup = withoutDrop[week] ?? [:]
                    lineup[candidate.id] = candidate.weekly[week] ?? 0
                    var lineupPositions = withoutDropPositions
                    lineupPositions[candidate.id] = candidate.position
                    let value = lineupTotal(lineup, lineupPositions, slots) - (baseline[week] ?? 0)
                    uplift += weight(week) * value
                }
                guard uplift > options.minUplift, let add = directory[candidate.id] else { continue }
                scored.append((
                    WaiverPick(
                        leagueID: league.leagueID,
                        leagueName: league.name,
                        addID: candidate.id,
                        addName: add.displayName,
                        addPosition: candidate.position,
                        addTeam: add.team,
                        dropID: dropID,
                        dropName: drop.displayName,
                        dropPosition: drop.position,
                        dropTeam: drop.team,
                        uplift: uplift
                    ),
                    uplift
                ))
            }
        }

        // One row per suggested add: the best drop for that player.
        var best: [String: (pick: WaiverPick, uplift: Double)] = [:]
        for entry in scored {
            if let current = best[entry.pick.addID], current.uplift >= entry.uplift { continue }
            best[entry.pick.addID] = entry
        }
        return best.values
            .sorted { $0.uplift > $1.uplift }
            .prefix(options.picksPerLeague)
            .map(\.pick)
    }

    // MARK: Helpers

    /// Greedy best-ball total: highest scorers get the first slot they fit,
    /// exactly like `BestBallEngine.assignSlots`.
    func lineupTotal(_ points: [String: Double], _ positions: [String: String], _ slots: [Slot]) -> Double {
        let ordered = points.keys.sorted {
            let lhs = points[$0] ?? 0
            let rhs = points[$1] ?? 0
            if lhs == rhs { return $0 < $1 }
            return lhs > rhs
        }
        var used = Set<String>()
        var total = 0.0
        for slot in slots where !slot.isBench {
            guard let playerID = ordered.first(where: {
                !used.contains($0) && slot.eligible.contains(positions[$0] ?? "")
            }) else { continue }
            used.insert(playerID)
            total += points[playerID] ?? 0
        }
        return total
    }

    /// Last week that matters, including the championship. Mirrors
    /// `fantasy_season_end_week` in the Streamlit app.
    static func seasonEndWeek(_ settings: SleeperLeague.Settings) -> Int {
        guard let start = settings.playoffWeekStart, start > 0,
              let teams = settings.playoffTeams, teams >= 2 else { return 18 }
        let rounds = Int(ceil(log2(Double(teams))))
        let duration = settings.playoffRoundType == 2 ? rounds * 2 : rounds + (settings.playoffRoundType == 1 ? 1 : 0)
        return min(18, start + duration - 1)
    }

    private func loadProjections(season: Int, weeks: ClosedRange<Int>) async -> [Int: StatTable] {
        let age = cacheAge
        let api = api
        return await withTaskGroup(of: (Int, StatTable?).self) { group in
            for week in weeks {
                group.addTask {
                    if let cached = SharedStore.loadProjections(season: season, week: week, maxAge: age) {
                        return (week, cached)
                    }
                    guard let table = try? await api.projections(season: season, week: week) else {
                        return (week, nil)
                    }
                    SharedStore.saveProjections(table, season: season, week: week)
                    return (week, table)
                }
            }
            var tables: [Int: StatTable] = [:]
            for await (week, table) in group {
                if let table { tables[week] = table }
            }
            return tables
        }
    }
}
