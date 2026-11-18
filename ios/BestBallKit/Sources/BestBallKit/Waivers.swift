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
    /// Average points gained per week over the rest of the season, playoff
    /// weeks counted 1.5x. Matches the uplift the Streamlit waiver guide shows.
    public let uplift: Double
    /// True for a real upgrade. Kept so reports cached before the iOS scanner
    /// applied the web guide's per-week filter still decode; new picks are
    /// always upgrades.
    public let isUpgrade: Bool

    /// Stable identity for "have I already been told about this one?".
    public var id: String { "\(leagueID)|\(addID)|\(dropID)" }

    public init(leagueID: String, leagueName: String, addID: String, addName: String,
                addPosition: String, addTeam: String, dropID: String, dropName: String,
                dropPosition: String, dropTeam: String, uplift: Double,
                isUpgrade: Bool = true) {
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
        self.isUpgrade = isUpgrade
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        leagueID = try container.decode(String.self, forKey: .leagueID)
        leagueName = (try? container.decode(String.self, forKey: .leagueName)) ?? ""
        addID = try container.decode(String.self, forKey: .addID)
        addName = (try? container.decode(String.self, forKey: .addName)) ?? addID
        addPosition = (try? container.decode(String.self, forKey: .addPosition)) ?? ""
        addTeam = (try? container.decode(String.self, forKey: .addTeam)) ?? ""
        dropID = try container.decode(String.self, forKey: .dropID)
        dropName = (try? container.decode(String.self, forKey: .dropName)) ?? dropID
        dropPosition = (try? container.decode(String.self, forKey: .dropPosition)) ?? ""
        dropTeam = (try? container.decode(String.self, forKey: .dropTeam)) ?? ""
        uplift = (try? container.decode(Double.self, forKey: .uplift)) ?? 0
        isUpgrade = (try? container.decode(Bool.self, forKey: .isUpgrade)) ?? (uplift > 0)
    }
}

public struct WaiverReport: Codable, Equatable, Sendable {
    /// The NFL week the projections start from.
    public let week: Int
    public let generated: Date
    public let picks: [WaiverPick]

    public init(week: Int, generated: Date, picks: [WaiverPick]) {
        self.week = week
        self.generated = generated
        self.picks = picks
    }
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
        /// Suggestions have to be worth more than this many points per week,
        /// weighted like the Streamlit guide's `best_uplift > 1`, to be shown.
        public var minUplift: Double

        public init(picksPerLeague: Int = 3, candidateLimit: Int = 40, minUplift: Double = 1.0) {
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

    /// Scans every league in parallel, returning the best suggestions across all
    /// of them, best first.
    public func scan(leagues: [LeagueSummary], userID: String, week: Int, season: Int) async -> [WaiverPick] {
        guard !leagues.isEmpty else { return [] }

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
        guard !details.isEmpty else { return [] }

        let endWeek = leagues.compactMap { details[$0.leagueID].map { Self.seasonEndWeek($0.settings) } }
            .reduce(18) { min(18, max($0, $1)) }
        let projections = await loadProjections(season: season, weeks: week...max(week, endWeek))
        guard !projections.isEmpty else { return [] }

        let directory = (try? await api.players()) ?? [:]
        guard !directory.isEmpty else { return [] }

        return await withTaskGroup(of: [WaiverPick].self) { group in
            for league in leagues {
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
    }

    // MARK: One league

    func scan(league: LeagueSummary, detail: SleeperLeague, directory: [String: SleeperPlayer],
              userID: String, week: Int, projections: [Int: StatTable]) async -> [WaiverPick] {
        guard let rosters = try? await api.rosters(leagueID: league.leagueID),
              let myRoster = rosters.first(where: { $0.ownerID == userID })?.players,
              !myRoster.isEmpty else { return [] }

        let rosterPositionList = myRoster.compactMap { directory[$0]?.position }
        guard !rosterPositionList.isEmpty else { return [] }

        // Same slot set as the web guide: one slot per player on the user's own
        // roster, not the league's starting lineup. See
        // `LineupSlots.rosterSlots` for why the Streamlit app ends up there.
        let slots = LineupSlots.rosterSlots(positions: rosterPositionList)
        let scoredPositions = Set(slots.flatMap(\.eligible))

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

        // The web only applies playoff weighting when the league actually sets
        // a playoff week; without one every week counts 1x.
        let playoffStart = detail.settings.playoffWeekStart
        func weight(_ week: Int) -> Double {
            guard let playoffStart, playoffStart > 0 else { return 1.0 }
            return week >= playoffStart ? 1.5 : 1.0
        }
        let totalWeight = weeks.reduce(0.0) { $0 + weight($1) }

        var weekly: [Int: [String: Double]] = [:]
        for week in weeks {
            let table = projections[week] ?? [:]
            var scored: [String: Double] = [:]
            for playerID in positions.keys { scored[playerID] = points(table, playerID) }
            weekly[week] = scored
        }
        let baseline = weekly.mapValues { lineupTotal($0, positions, slots) }

        // The web filters its pool to `settings.relevant_positions`, which with
        // roster slots is exactly the set of positions the user rosters — a
        // kicker when you carry no kicker can't help any lineup.

        // Free agents: everyone with a projection who nobody in this league owns.
        let rostered = Set(rosters.flatMap(\.players))
        var candidates: [(id: String, position: String, weekly: [Int: Double], total: Double)] = []
        for (playerID, player) in directory {
            guard !rostered.contains(playerID),
                  Self.waiverPositions.contains(player.position),
                  scoredPositions.contains(player.position) else { continue }
            var scored: [Int: Double] = [:]
            var total = 0.0
            for week in weeks {
                let value = points(projections[week] ?? [:], playerID)
                scored[week] = value
                total += value * weight(week)
            }
            // A candidate's own average sets the ceiling on its uplift, so
            // anything at zero can't clear the guide's threshold.
            guard total / totalWeight > 0 else { continue }
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
                // Same filter as the Streamlit guide: the weighted average must
                // beat one point per week, not a season-long sum.
                let averageUplift = uplift / totalWeight
                guard averageUplift > options.minUplift else { continue }
                guard let add = directory[candidate.id] else { continue }
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
                        uplift: averageUplift
                    ),
                    averageUplift
                ))
            }
        }

        // One row per suggested add: the best drop for that player.
        var best: [String: (pick: WaiverPick, uplift: Double)] = [:]
        for entry in scored {
            if let current = best[entry.pick.addID], current.uplift >= entry.uplift { continue }
            best[entry.pick.addID] = entry
        }
        let ranked = best.values.sorted { $0.uplift > $1.uplift }

        // Like the Streamlit guide, an empty wire means no suggestions at all
        // rather than a padded "best available" list.
        return ranked
            .filter { $0.uplift > options.minUplift }
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
