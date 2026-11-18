import Foundation

// MARK: - Models

/// One player in a trade. `projection` is the weighted average weekly
/// projection across the weeks the scan scored, standing in for the P50/P90
/// columns the Streamlit trade table shows.
public struct TradeAsset: Codable, Hashable, Identifiable, Sendable {
    public let id: String
    public let name: String
    public let position: String
    public let team: String
    public let projection: Double

    public init(id: String, name: String, position: String, team: String, projection: Double) {
        self.id = id
        self.name = name
        self.position = position
        self.team = team
        self.projection = projection
    }

    /// The small detail line under a player's name: "RB - KC · Proj 12.3".
    public var detailText: String {
        var parts: [String] = []
        let teamLine = "\(position) - \(team)".trimmingCharacters(in: CharacterSet(charactersIn: " -"))
        if !teamLine.isEmpty { parts.append(teamLine) }
        if projection > 0 { parts.append(String(format: "Proj %.1f", projection)) }
        return parts.joined(separator: " · ")
    }
}

/// One two-team offer: what you send out and what you get back, with the
/// projected weekly gain for each side.
public struct TradeOffer: Codable, Hashable, Identifiable, Sendable {
    public let leagueID: String
    public let leagueName: String
    public let partnerID: String
    public let partnerName: String
    public let give: [TradeAsset]
    public let receive: [TradeAsset]
    /// Weighted points per week this deal adds to your lineup.
    public let myUplift: Double
    /// Weighted points per week this deal adds to the partner's lineup.
    public let partnerUplift: Double

    public var totalUplift: Double { myUplift + partnerUplift }

    public var id: String {
        let out = give.map(\.id).joined(separator: "+")
        let back = receive.map(\.id).joined(separator: "+")
        return "\(leagueID)|\(partnerID)|\(out)|\(back)"
    }

    public init(leagueID: String, leagueName: String, partnerID: String, partnerName: String,
                give: [TradeAsset], receive: [TradeAsset],
                myUplift: Double, partnerUplift: Double) {
        self.leagueID = leagueID
        self.leagueName = leagueName
        self.partnerID = partnerID
        self.partnerName = partnerName
        self.give = give
        self.receive = receive
        self.myUplift = myUplift
        self.partnerUplift = partnerUplift
    }
}

/// A roster the analyzer can pick.
public struct TradeTeam: Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let assets: [TradeAsset]

    public init(id: String, name: String, assets: [TradeAsset]) {
        self.id = id
        self.name = name
        self.assets = assets
    }
}

/// Everything one league's analyzer needs: the teams, the lineup slots, and
/// every rostered player's scored projection per week. Offers are computed on
/// demand so the Trade Analyzer can answer any team pairing locally instead of
/// waiting on another scan.
public struct TradeBoard: Identifiable, Sendable {
    public let id: String
    public let name: String
    public let teams: [TradeTeam]
    public let userTeamID: String?
    public let slots: [Slot]
    public let weeks: [Int]
    /// Playoff weeks count 1.5x, like the Streamlit analyzer.
    public let weights: [Double]
    /// Week -> player id -> projected points in this league's scoring.
    public let weekly: [Int: [String: Double]]

    public init(id: String, name: String, teams: [TradeTeam], userTeamID: String?,
                slots: [Slot], weeks: [Int], weights: [Double],
                weekly: [Int: [String: Double]]) {
        self.id = id
        self.name = name
        self.teams = teams
        self.userTeamID = userTeamID
        self.slots = slots
        self.weeks = weeks
        self.weights = weights
        self.weekly = weekly
    }

    public var totalWeight: Double { weights.reduce(0, +) }

    /// Positions that appear on any roster, sorted for the need pickers.
    public var positions: [String] {
        Array(Set(teams.flatMap { $0.assets.map(\.position) })).sorted()
    }

    public func team(_ teamID: String) -> TradeTeam? {
        teams.first { $0.id == teamID }
    }

    public var userTeam: TradeTeam? {
        userTeamID.flatMap(team)
    }

    /// Every offer between two teams that helps both of them.
    ///
    /// A port of `_compute_trade_recommendations` in the Streamlit app: every
    /// single-player swap is scored, plus packages built from the top eight
    /// projected players on each roster. `minUplift` is points per week each
    /// side has to clear — the league-wide list uses 1.0, the analyzer uses 0,
    /// which keeps any strictly positive gain.
    public func analyze(
        myTeamID: String,
        partnerTeamID: String,
        myNeed: String? = nil,
        partnerNeed: String? = nil,
        minUplift: Double = 0
    ) -> [TradeOffer] {
        guard myTeamID != partnerTeamID,
              let myTeam = team(myTeamID),
              let partnerTeam = team(partnerTeamID),
              !myTeam.assets.isEmpty, !partnerTeam.assets.isEmpty,
              !weeks.isEmpty, totalWeight > 0 else { return [] }

        let myBaseline = baselinePoints(for: myTeam)
        let partnerBaseline = baselinePoints(for: partnerTeam)
        let myStates = states(for: myTeam)
        let partnerStates = states(for: partnerTeam)
        let threshold = minUplift * totalWeight

        var offers: [TradeOffer] = []
        for give in myStates {
            // A position need means every player that side receives has to
            // play it, so the players going out are the ones filtered.
            if let partnerNeed, give.assets.contains(where: { $0.position != partnerNeed }) {
                continue
            }
            for receive in partnerStates {
                if let myNeed, receive.assets.contains(where: { $0.position != myNeed }) {
                    continue
                }

                var mySum = 0.0
                var partnerSum = 0.0
                for (index, weight) in weights.enumerated() {
                    let myAfter = LineupScorer.total(
                        positions: give.remainingPositions + receive.incomingPositions,
                        points: give.remainingPoints[index] + receive.incomingPoints[index],
                        slots: slots
                    )
                    let partnerAfter = LineupScorer.total(
                        positions: receive.remainingPositions + give.incomingPositions,
                        points: receive.remainingPoints[index] + give.incomingPoints[index],
                        slots: slots
                    )
                    mySum += weight * (myAfter - myBaseline[index])
                    partnerSum += weight * (partnerAfter - partnerBaseline[index])
                }

                guard mySum > threshold, partnerSum > threshold else { continue }

                offers.append(
                    TradeOffer(
                        leagueID: id,
                        leagueName: name,
                        partnerID: partnerTeam.id,
                        partnerName: partnerTeam.name,
                        give: give.assets,
                        receive: receive.assets,
                        myUplift: mySum / totalWeight,
                        partnerUplift: partnerSum / totalWeight
                    )
                )
            }
        }

        return offers.sorted {
            if $0.myUplift != $1.myUplift { return $0.myUplift > $1.myUplift }
            return $0.partnerUplift > $1.partnerUplift
        }
    }

    // MARK: Scoring state

    /// One candidate package leaving a roster, with that roster's lineup
    /// pre-split into who stays and who goes for each scored week.
    private struct ChoiceState {
        let assets: [TradeAsset]
        let remainingPositions: [String]
        let remainingPoints: [[Double]]
        let incomingPositions: [String]
        let incomingPoints: [[Double]]
    }

    private func points(_ assetID: String, week: Int) -> Double {
        weekly[week]?[assetID] ?? 0
    }

    /// Weighted rest-of-season total, used to rank package candidates.
    private func weightedTotal(_ asset: TradeAsset) -> Double {
        var total = 0.0
        for (index, week) in weeks.enumerated() {
            total += weights[index] * points(asset.id, week: week)
        }
        return total
    }

    /// Every single-player swap plus pairs of the top eight players, exactly
    /// like `packages()` in the Streamlit app.
    private func packages(_ assets: [TradeAsset], limit: Int) -> [[TradeAsset]] {
        var result: [[TradeAsset]] = assets.map { [$0] }
        let ranked = assets
            .enumerated()
            .sorted { lhs, rhs in
                let left = weightedTotal(lhs.element)
                let right = weightedTotal(rhs.element)
                if left == right { return lhs.offset < rhs.offset }
                return left > right
            }
            .prefix(limit)
            .map(\.element)
        for i in ranked.indices {
            for j in ranked.indices where j > i {
                result.append([ranked[i], ranked[j]])
            }
        }
        return result
    }

    private func baselinePoints(for team: TradeTeam) -> [Double] {
        let positions = team.assets.map(\.position)
        return weeks.map { week in
            LineupScorer.total(
                positions: positions,
                points: team.assets.map { points($0.id, week: week) },
                slots: slots
            )
        }
    }

    private func states(for team: TradeTeam, packageLimit: Int = 8) -> [ChoiceState] {
        packages(team.assets, limit: packageLimit).map { outgoing in
            let outgoingIDs = Set(outgoing.map(\.id))
            let remaining = team.assets.filter { !outgoingIDs.contains($0.id) }
            return ChoiceState(
                assets: outgoing,
                remainingPositions: remaining.map(\.position),
                remainingPoints: weeks.map { week in
                    remaining.map { points($0.id, week: week) }
                },
                incomingPositions: outgoing.map(\.position),
                incomingPoints: weeks.map { week in
                    outgoing.map { points($0.id, week: week) }
                }
            )
        }
    }
}

/// One scan across every league: the strongest offers, plus the boards the
/// Trade Analyzer works from.
public struct TradeScan: Sendable {
    public let week: Int
    public let generated: Date
    public let offers: [TradeOffer]
    public let boards: [TradeBoard]

    public init(week: Int, generated: Date, offers: [TradeOffer], boards: [TradeBoard]) {
        self.week = week
        self.generated = generated
        self.offers = offers
        self.boards = boards
    }
}

// MARK: - Lineup scoring

/// Greedy best-ball total: highest scorers get the first slot they fit, the
/// same walk `_best_lineup_score` does in the Streamlit app.
enum LineupScorer {
    static func total(positions: [String], points: [Double], slots: [Slot]) -> Double {
        guard !points.isEmpty else { return 0 }
        let order = points.indices.sorted { lhs, rhs in
            if points[lhs] == points[rhs] { return lhs < rhs }
            return points[lhs] > points[rhs]
        }
        var used = [Bool](repeating: false, count: points.count)
        var total = 0.0
        for slot in slots where !slot.isBench {
            for index in order where !used[index] {
                guard slot.eligible.contains(positions[index]) else { continue }
                used[index] = true
                total += points[index]
                break
            }
        }
        return total
    }
}

// MARK: - Scanner

/// Finds win-win trades across every league, mirroring the Streamlit app's
/// Trade Suggestions view. A trimmed-down port of `compute_trade_recommendations`.
public struct TradeScanner: Sendable {
    public struct Options: Sendable {
        /// Weekly points each side has to gain for the league-wide list, the
        /// web guide's default threshold.
        public var minUplift: Double
        /// Offers kept per trade partner, matching the web table's top five.
        public var offersPerPartner: Int

        public init(minUplift: Double = 1.0, offersPerPartner: Int = 5) {
            self.minUplift = minUplift
            self.offersPerPartner = offersPerPartner
        }
    }

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

    /// Scans every league in parallel. Leagues that fail are skipped rather than
    /// failing the whole scan.
    public func scan(leagues: [LeagueSummary], userID: String,
                     week: Int, season: Int) async -> TradeScan {
        let empty = TradeScan(week: week, generated: Date(), offers: [], boards: [])
        guard !leagues.isEmpty else { return empty }

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
        guard !details.isEmpty else { return empty }

        let endWeek = leagues
            .compactMap { details[$0.leagueID].map { WaiverScanner.seasonEndWeek($0.settings) } }
            .reduce(18) { min(18, max($0, $1)) }
        let projections = await loadProjections(season: season, weeks: week...max(week, endWeek))
        guard !projections.isEmpty else { return empty }

        let directory = (try? await api.players()) ?? [:]
        guard !directory.isEmpty else { return empty }

        let results = await withTaskGroup(of: (offers: [TradeOffer], board: TradeBoard?).self) { group in
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
            var found: [(offers: [TradeOffer], board: TradeBoard?)] = []
            for await result in group { found.append(result) }
            return found
        }

        let boards = results.compactMap(\.board)
        let offers = results.flatMap(\.offers).sorted {
            if $0.myUplift != $1.myUplift { return $0.myUplift > $1.myUplift }
            return $0.partnerUplift > $1.partnerUplift
        }
        return TradeScan(week: week, generated: Date(), offers: offers, boards: boards)
    }

    // MARK: One league

    func scan(league: LeagueSummary, detail: SleeperLeague,
              directory: [String: SleeperPlayer], userID: String, week: Int,
              projections: [Int: StatTable]) async -> (offers: [TradeOffer], board: TradeBoard?) {
        guard let rosters = try? await api.rosters(leagueID: league.leagueID),
              rosters.contains(where: { $0.ownerID == userID }) else { return ([], nil) }

        let slots = LineupSlots.slots(for: detail.rosterPositions)
        guard slots.contains(where: { !$0.isBench }) else { return ([], nil) }

        let weeks = (week...max(week, WaiverScanner.seasonEndWeek(detail.settings))).filter {
            $0 <= 18 && projections[$0] != nil
        }
        guard !weeks.isEmpty else { return ([], nil) }

        let playoffStart = detail.settings.playoffWeekStart ?? 15
        let weights = weeks.map { $0 >= playoffStart ? 1.5 : 1.0 }
        let totalWeight = weights.reduce(0, +)

        let scoring = detail.scoringSettings
        func points(_ table: StatTable, _ playerID: String) -> Double {
            guard let stats = table[playerID] else { return 0 }
            return Scoring.points(stats: stats, scoring: scoring)
        }

        // Every rostered player's scored projection per week, used for both the
        // offers and the analyzer's board.
        var weekly: [Int: [String: Double]] = [:]
        for week in weeks {
            let table = projections[week] ?? [:]
            var scored: [String: Double] = [:]
            for playerID in rosters.flatMap(\.players) {
                scored[playerID] = points(table, playerID)
            }
            weekly[week] = scored
        }

        func assets(for roster: SleeperRoster) -> [TradeAsset] {
            roster.players.compactMap { playerID in
                guard let player = directory[playerID] else { return nil }
                var projection = 0.0
                for (index, week) in weeks.enumerated() {
                    projection += weights[index] * (weekly[week]?[playerID] ?? 0)
                }
                return TradeAsset(
                    id: playerID,
                    name: player.displayName,
                    position: player.position,
                    team: player.team,
                    projection: totalWeight > 0 ? projection / totalWeight : 0
                )
            }
        }

        let teams: [TradeTeam] = rosters.compactMap { roster in
            let players = assets(for: roster)
            guard !players.isEmpty else { return nil }
            let name = roster.teamName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return TradeTeam(
                id: String(roster.rosterID),
                name: name.isEmpty ? "Team \(roster.rosterID)" : name,
                assets: players
            )
        }
        guard teams.count > 1 else { return ([], nil) }

        let userTeamID = rosters.first { $0.ownerID == userID }.map { String($0.rosterID) }
        let board = TradeBoard(
            id: league.leagueID,
            name: league.name,
            teams: teams,
            userTeamID: userTeamID,
            slots: slots,
            weeks: weeks,
            weights: weights,
            weekly: weekly
        )

        let myTeamID = userTeamID ?? teams[0].id
        var offers: [TradeOffer] = []
        for partner in teams where partner.id != myTeamID {
            let found = board.analyze(
                myTeamID: myTeamID,
                partnerTeamID: partner.id,
                minUplift: options.minUplift
            )
            offers.append(contentsOf: found.prefix(options.offersPerPartner))
        }
        return (offers, board)
    }

    // MARK: Projections

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
