import Foundation

// MARK: - Models

/// One player in a trade. `p50`/`p90` are the season projections the Streamlit
/// trade table prints under each name: the median weekly score and the mean
/// plus 1.2816 standard deviations across weeks 1-18.
public struct TradeAsset: Codable, Hashable, Identifiable, Sendable {
    public let id: String
    public let name: String
    public let position: String
    public let team: String
    public let p50: Double
    public let p90: Double

    public init(id: String, name: String, position: String, team: String,
                p50: Double = 0, p90: Double = 0) {
        self.id = id
        self.name = name
        self.position = position
        self.team = team
        self.p50 = p50
        self.p90 = p90
    }

    /// The small detail line under a player's name, same shape as
    /// `player_detail_text` in the Streamlit app: "RB - KC · P50 12.3 · P90 18.9".
    public var detailText: String {
        var parts: [String] = []
        let teamLine = "\(position) - \(team)".trimmingCharacters(in: CharacterSet(charactersIn: " -"))
        if !teamLine.isEmpty { parts.append(teamLine) }
        if p50 != 0 { parts.append(String(format: "P50 %.1f", p50)) }
        if p90 != 0 { parts.append(String(format: "P90 %.1f", p90)) }
        return parts.joined(separator: " · ")
    }

    /// Sleeper web profile for the player, like `sleeper_player_url` on the web.
    public var profileURL: URL? {
        SleeperProfile.url(name: name, id: id)
    }
}

/// Where a player's Sleeper page lives on the web, built the way
/// `sleeper_player_url` does in the Streamlit app. Sleeper's app registers no
/// per-player deep link (its universal links cover only its chat pages), so the
/// web profile is the only address that resolves to a player.
public enum SleeperProfile {
    public static func url(name: String, id: String) -> URL? {
        guard !id.isEmpty else { return nil }
        let slug = name.lowercased()
            .replacingOccurrences(of: "[^a-z0-9]+", with: "-", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        let escaped = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
        return URL(string: "https://sleeper.com/nfl/players/\(slug)-\(escaped)")
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
    /// Players padded onto each side so the two packages hold the same number
    /// of players. They are the ones that side would most likely cut, so the
    /// deal doesn't leave anyone over the roster limit afterwards.
    public let giveThrowIns: [String]
    public let receiveThrowIns: [String]

    public var totalUplift: Double { myUplift + partnerUplift }

    /// Throw-in ids on both sides, for the row that tags them.
    public var throwInIDs: Set<String> { Set(giveThrowIns + receiveThrowIns) }

    /// Balanced packages: one player each way, or two apiece. Sleeper leagues
    /// keep roster sizes equal, so an uneven package is not the deal either
    /// manager would actually make.
    public var isBalanced: Bool { give.count == receive.count }

    public var id: String {
        let out = give.map(\.id).joined(separator: "+")
        let back = receive.map(\.id).joined(separator: "+")
        return "\(leagueID)|\(partnerID)|\(out)|\(back)"
    }

    public init(leagueID: String, leagueName: String, partnerID: String, partnerName: String,
                give: [TradeAsset], receive: [TradeAsset],
                myUplift: Double, partnerUplift: Double,
                giveThrowIns: [String] = [], receiveThrowIns: [String] = []) {
        self.leagueID = leagueID
        self.leagueName = leagueName
        self.partnerID = partnerID
        self.partnerName = partnerName
        self.give = give
        self.receive = receive
        self.myUplift = myUplift
        self.partnerUplift = partnerUplift
        self.giveThrowIns = giveThrowIns
        self.receiveThrowIns = receiveThrowIns
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

    /// The slot set the Streamlit app scores trades with — see
    /// `LineupSlots.rosterSlots`.
    public static func rosterSlots(for assets: [TradeAsset]) -> [Slot] {
        LineupSlots.rosterSlots(positions: assets.map(\.position))
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
    ///
    /// The slot set stays the user's roster (see `rosterSlots`), like the web.
    /// One deliberate difference: a package that sends two players for one is
    /// padded with the throw-in that side would otherwise have to cut, so the
    /// offer on screen is the deal both managers could actually accept. The
    /// web leaves those packages uneven.
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
        let threshold = minUplift * totalWeight

        // Wrap-up packages are rescored many times once throw-ins are attached,
        // so keep the per-package week arrays around.
        var cache: [String: ChoiceState] = [:]
        func state(_ assets: [TradeAsset], of team: TradeTeam) -> ChoiceState {
            let key = team.id + "|" + assets.map(\.id).sorted().joined(separator: ",")
            if let hit = cache[key] { return hit }
            let outgoingIDs = Set(assets.map(\.id))
            let remaining = team.assets.filter { !outgoingIDs.contains($0.id) }
            let made = ChoiceState(
                assets: assets,
                remainingPositions: remaining.map(\.position),
                remainingPoints: weeks.map { week in remaining.map { points($0.id, week: week) } },
                incomingPositions: assets.map(\.position),
                incomingPoints: weeks.map { week in assets.map { points($0.id, week: week) } }
            )
            cache[key] = made
            return made
        }

        var seen = Set<String>()
        var offers: [TradeOffer] = []
        for giveBase in packages(myTeam.assets, limit: 8) {
            for receiveBase in packages(partnerTeam.assets, limit: 8) {
                // Square up the player counts with the throw-ins each side would
                // cut anyway, so neither manager ends up over the roster limit.
                var give = giveBase
                var receive = receiveBase
                var giveThrowIns: [TradeAsset] = []
                var receiveThrowIns: [TradeAsset] = []
                let shortfall = receiveBase.count - giveBase.count
                if shortfall > 0 {
                    guard let padding = throwIns(for: myTeam, count: shortfall,
                                                 excluding: Set(giveBase.map(\.id))) else { continue }
                    give += padding
                    giveThrowIns = padding
                } else if shortfall < 0 {
                    guard let padding = throwIns(for: partnerTeam, count: -shortfall,
                                                 excluding: Set(receiveBase.map(\.id))) else { continue }
                    receive += padding
                    receiveThrowIns = padding
                }

                // A position need still means every player in the package plays
                // it, throw-ins included, like the web's analyzer.
                if let partnerNeed, give.contains(where: { $0.position != partnerNeed }) {
                    continue
                }
                if let myNeed, receive.contains(where: { $0.position != myNeed }) {
                    continue
                }

                let key = give.map(\.id).sorted().joined(separator: ",") + "->"
                    + receive.map(\.id).sorted().joined(separator: ",")
                guard seen.insert(key).inserted else { continue }

                let myState = state(give, of: myTeam)
                let partnerState = state(receive, of: partnerTeam)

                var mySum = 0.0
                var partnerSum = 0.0
                for (index, weight) in weights.enumerated() {
                    let myAfter = LineupScorer.total(
                        positions: myState.remainingPositions + partnerState.incomingPositions,
                        points: myState.remainingPoints[index] + partnerState.incomingPoints[index],
                        slots: slots
                    )
                    let partnerAfter = LineupScorer.total(
                        positions: partnerState.remainingPositions + myState.incomingPositions,
                        points: partnerState.remainingPoints[index] + myState.incomingPoints[index],
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
                        give: give,
                        receive: receive,
                        myUplift: mySum / totalWeight,
                        partnerUplift: partnerSum / totalWeight,
                        giveThrowIns: giveThrowIns.map(\.id),
                        receiveThrowIns: receiveThrowIns.map(\.id)
                    )
                )
            }
        }

        return offers.sorted {
            if $0.myUplift != $1.myUplift { return $0.myUplift > $1.myUplift }
            return $0.partnerUplift > $1.partnerUplift
        }
    }

    /// The players a manager would most likely cut, weakest projected
    /// rest-of-season total first. Used to pad an uneven package, and nil when
    /// the roster cannot spare that many.
    private func throwIns(for team: TradeTeam, count: Int,
                          excluding ids: Set<String>) -> [TradeAsset]? {
        guard count > 0 else { return [] }
        let pool = team.assets
            .filter { !ids.contains($0.id) }
            .sorted { lhs, rhs in
                let left = weightedTotal(lhs)
                let right = weightedTotal(rhs)
                if left == right { return lhs.id < rhs.id }
                return left < right
            }
        guard pool.count >= count else { return nil }
        return Array(pool.prefix(count))
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

        // The whole regular season, like `build_projection_inputs` on the web: the
        // season P50/P90 lines are built from weeks 1-18, not just the weeks
        // still to be played.
        let projections = await loadProjections(season: season, weeks: 1...18)
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
              let myRoster = rosters.first(where: { $0.ownerID == userID }) else { return ([], nil) }

        let users = (try? await api.users(leagueID: league.leagueID)) ?? []
        let usersByID = Dictionary(users.map { ($0.userID, $0) }, uniquingKeysWith: { first, _ in first })

        let seasonEnd = WaiverScanner.seasonEndWeek(detail.settings)
        let scoredWeeks = (1...18).filter { projections[$0] != nil }
        let weeks = scoredWeeks.filter { $0 >= week && $0 <= seasonEnd }
        guard !weeks.isEmpty else { return ([], nil) }

        // Only a league that actually defines a playoff start weights those weeks
        // at 1.5, matching `_compute_trade_recommendations`.
        let playoffStart = detail.settings.playoffWeekStart
        let weights = weeks.map { scored in
            if let playoffStart, scored >= playoffStart { return 1.5 }
            return 1.0
        }
        let scoring = detail.scoringSettings
        func points(_ table: StatTable, _ playerID: String) -> Double {
            guard let stats = table[playerID] else { return 0 }
            return Scoring.points(stats: stats, scoring: scoring)
        }

        let rosteredIDs = rosters.flatMap(\.players)

        // Every rostered player's scored projection per week, used for both the
        // offers and the analyzer's board.
        var weekly: [Int: [String: Double]] = [:]
        for scored in weeks {
            let table = projections[scored] ?? [:]
            var values: [String: Double] = [:]
            for playerID in rosteredIDs {
                values[playerID] = points(table, playerID)
            }
            weekly[scored] = values
        }

        // Season P50/P90 across every week with projection data, built the way
        // `build_season_projections` does: median, mean + 1.2816 * std.
        var seasonLines: [String: (p50: Double, p90: Double)] = [:]
        for playerID in rosteredIDs {
            var values: [Double] = []
            for scored in scoredWeeks {
                guard let table = projections[scored], table[playerID] != nil else { continue }
                values.append(points(table, playerID))
            }
            guard values.count > 1 else {
                seasonLines[playerID] = (values.first ?? 0, values.first ?? 0)
                continue
            }
            let sorted = values.sorted()
            let middle = sorted.count / 2
            let median = sorted.count % 2 == 0
                ? (sorted[middle - 1] + sorted[middle]) / 2
                : sorted[middle]
            let mean = values.reduce(0, +) / Double(values.count)
            let variance = values.reduce(0) { $0 + ($1 - mean) * ($1 - mean) } / Double(values.count - 1)
            seasonLines[playerID] = (median, mean + 1.2816 * variance.squareRoot())
        }

        func assets(for roster: SleeperRoster) -> [TradeAsset] {
            roster.players.compactMap { playerID in
                guard let player = directory[playerID] else { return nil }
                let lines = seasonLines[playerID] ?? (0, 0)
                return TradeAsset(
                    id: playerID,
                    name: player.displayName,
                    position: player.position,
                    team: player.team,
                    p50: lines.p50,
                    p90: lines.p90
                )
            }
        }

        // Team names the way the web's roster table builds them: the Sleeper team
        // name when the league set one, else the owner's display name, else
        // "Team <roster id>".
        func teamName(_ roster: SleeperRoster) -> String {
            let custom = roster.teamName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !custom.isEmpty { return custom }
            if let owner = roster.ownerID.flatMap({ usersByID[$0] }) {
                let display = owner.displayName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                if !display.isEmpty { return display }
                let username = owner.username?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                if !username.isEmpty { return username }
            }
            return "Team \(roster.rosterID)"
        }

        let teams: [TradeTeam] = rosters.compactMap { roster in
            let players = assets(for: roster)
            guard !players.isEmpty else { return nil }
            return TradeTeam(id: String(roster.rosterID), name: teamName(roster), assets: players)
        }
        guard teams.count > 1 else { return ([], nil) }

        let myAssets = assets(for: myRoster)
        // Trades are scored against the league's real starting lineup, not the
        // web's `from_actual_roster` fallback (see `TradeBoard.rosterSlots`).
        // Under the fallback a trade is almost zero-sum — every rostered player
        // owns a slot — so only one partner in a league ever had a mutually
        // profitable package. A real lineup gives both sides bench players worth
        // nothing to them and starters worth something to the other team.
        let slots = LineupSlots.slots(for: detail.rosterPositions)
        guard !slots.isEmpty else { return ([], nil) }

        let userTeamID = String(myRoster.rosterID)
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

        let myTeamID = userTeamID
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
