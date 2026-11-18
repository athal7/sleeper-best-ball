import Foundation

// MARK: - Slots

public struct Slot: Hashable, Sendable {
    public let label: String
    public let position: String
    public let eligible: Set<String>

    public init(label: String, position: String, eligible: Set<String>) {
        self.label = label
        self.position = position
        self.eligible = eligible
    }

    public var isBench: Bool { position == "BN" }
}

public enum LineupSlots {
    /// Same slot order and eligibility as `Positions.MAPPINGS` in the
    /// Streamlit app. Slots are filled in this order.
    public static let order = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "K", "DEF", "BN"]

    public static let eligibility: [String: Set<String>] = [
        "QB": ["QB"],
        "RB": ["RB"],
        "WR": ["WR"],
        "TE": ["TE"],
        "FLEX": ["RB", "WR", "TE"],
        "SUPER_FLEX": ["QB", "RB", "WR", "TE"],
        "K": ["K"],
        "DEF": ["DEF"],
        "BN": ["QB", "RB", "WR", "TE", "K", "DEF"],
    ]

    /// Expands Sleeper's `roster_positions` list (e.g. `["QB", "RB", "RB",
    /// "WR", "FLEX", "BN", ...]`) into labelled slots: QB1, RB1, RB2, FLEX1,
    /// BN1, ... Unknown slots are ignored, matching the Python app.
    public static func slots(for rosterPositions: [String]) -> [Slot] {
        var slots: [Slot] = []
        var counters: [String: Int] = [:]
        for position in order {
            let count = rosterPositions.filter { $0 == position }.count
            guard count > 0, let eligible = eligibility[position] else { continue }
            for _ in 0..<count {
                let number = (counters[position] ?? 0) + 1
                counters[position] = number
                slots.append(Slot(label: "\(position)\(number)", position: position, eligible: eligible))
            }
        }
        return slots
    }

    /// The slot set the Streamlit app actually scores waivers and trades with.
    ///
    /// `DraftSettings.from_draft` reads `slots_qb`-style keys that real Sleeper
    /// leagues do not have, so the web path falls through to
    /// `DraftSettings.from_actual_roster`: one slot per player the *user's own*
    /// roster carries, each slot eligible only for that position. Every rostered
    /// player therefore scores, bench included, and no flex slot exists. Rebuild
    /// the same set here so the two apps agree to the decimal.
    public static func rosterSlots(positions: [String]) -> [Slot] {
        var counts: [String: Int] = [:]
        var order: [String] = []
        for position in positions {
            if counts[position] == nil { order.append(position) }
            counts[position, default: 0] += 1
        }
        return order.flatMap { position in
            (0..<(counts[position] ?? 0)).map { index in
                Slot(label: "\(position)\(index + 1)", position: position, eligible: [position])
            }
        }
    }
}

// MARK: - Rostered players

public struct RosterPlayer: Identifiable, Hashable, Sendable {
    public let id: String
    public let firstName: String
    public let lastName: String
    public let position: String
    public let team: String
    public let injuryStatus: String?
    public let points: Double
    public let projection: Double
    public let optimistic: Double
    public let pctPlayed: Double
    public let bye: Bool
    public let opponent: String
    public let isHome: Bool
    public let gameStatus: String
    public let gameTime: Date?
    public let score: Double?
    public let opponentScore: Double?
    /// Slot in the best-ball (optimistic) lineup. Bench slots start with "BN".
    public let slot: String
    /// Slot this player currently occupies in Sleeper's starting lineup.
    public let currentSlot: String

    public var name: String {
        guard !firstName.isEmpty, !lastName.isEmpty else {
            return lastName.isEmpty ? firstName : lastName
        }
        return "\(firstName.prefix(1)). \(lastName)"
    }

    public var isBench: Bool { slot.hasPrefix("BN") }
    public var isLive: Bool { pctPlayed > 0 && pctPlayed < 1 }
    public var isFinal: Bool { pctPlayed >= 1 }

    public var pointsText: String { points == 0 ? "–" : String(format: "%.2f", points) }

    /// Matches `Player.get_projection`: a finished player shows their real
    /// projection, everyone else shows the optimistic one.
    public var projectionText: String {
        guard projection != 0 else { return "–" }
        return String(format: "%.2f", isFinal ? projection : optimistic)
    }

    public var infoText: String {
        var info = "\(position) · \(team)"
        if let injuryStatus, !injuryStatus.isEmpty {
            let shortened: String
            switch injuryStatus {
            case "Probable": shortened = "P"
            case "Questionable": shortened = "Q"
            case "Doubtful": shortened = "D"
            case "Out": shortened = "O"
            case "IR": shortened = "IR"
            default: shortened = injuryStatus
            }
            info += " (\(shortened))"
        }
        return info
    }

    public var statusText: String {
        if bye { return "Bye" }
        let versus = isHome ? "vs" : "@"
        if pctPlayed == 0, let gameTime {
            return "\(gameTime.formatted(.dateTime.weekday(.abbreviated).hour().minute())) \(versus) \(opponent)"
        }
        let status = gameStatus.isEmpty ? "Live" : gameStatus
        return "\(status) \(scoreText)-\(opponentScoreText) \(versus) \(opponent)"
    }

    private var scoreText: String { score.map { String(format: "%.0f", $0) } ?? "0" }
    private var opponentScoreText: String { opponentScore.map { String(format: "%.0f", $0) } ?? "0" }

    public init(id: String, firstName: String, lastName: String, position: String,
                team: String, injuryStatus: String?, points: Double, projection: Double,
                optimistic: Double, pctPlayed: Double, bye: Bool, opponent: String,
                isHome: Bool, gameStatus: String, gameTime: Date?, score: Double?,
                opponentScore: Double?, slot: String, currentSlot: String) {
        self.id = id
        self.firstName = firstName
        self.lastName = lastName
        self.position = position
        self.team = team
        self.injuryStatus = injuryStatus
        self.points = points
        self.projection = projection
        self.optimistic = optimistic
        self.pctPlayed = pctPlayed
        self.bye = bye
        self.opponent = opponent
        self.isHome = isHome
        self.gameStatus = gameStatus
        self.gameTime = gameTime
        self.score = score
        self.opponentScore = opponentScore
        self.slot = slot
        self.currentSlot = currentSlot
    }

    func withSlots(slot: String, currentSlot: String) -> RosterPlayer {
        RosterPlayer(
            id: id, firstName: firstName, lastName: lastName, position: position,
            team: team, injuryStatus: injuryStatus, points: points,
            projection: projection, optimistic: optimistic, pctPlayed: pctPlayed,
            bye: bye, opponent: opponent, isHome: isHome, gameStatus: gameStatus,
            gameTime: gameTime, score: score, opponentScore: opponentScore,
            slot: slot, currentSlot: currentSlot
        )
    }
}

// MARK: - Engine

public enum BestBallEngine {
    /// Builds the per-player rows for one roster. Mirrors `League.players()`:
    /// fantasy points come from this week's stats, projections from this
    /// week's raw projections, and the optimistic total assumes every
    /// unplayed moment of a game will hit that projection.
    public static func players(
        playerIDs: [String],
        directory: [String: SleeperPlayer],
        stats: StatTable,
        projections: StatTable,
        scoring: [String: Double],
        games: [String: TeamGame],
        gamesAvailable: Bool
    ) -> [RosterPlayer] {
        playerIDs.compactMap { playerID -> RosterPlayer? in
            guard let player = directory[playerID] else { return nil }
            let statLine = stats[playerID] ?? [:]
            let projectionLine = projections[playerID] ?? [:]
            let points = Scoring.points(stats: statLine, scoring: scoring)
            let projection = Scoring.points(stats: projectionLine, scoring: scoring)
            let game = games[player.team]
            let pctPlayed = game?.pctPlayed ?? 0
            let bye = gamesAvailable && game == nil

            return RosterPlayer(
                id: playerID,
                firstName: player.firstName,
                lastName: player.lastName,
                position: player.position,
                team: player.team,
                injuryStatus: player.injuryStatus,
                points: points,
                projection: projection,
                optimistic: points + (1 - pctPlayed) * projection,
                pctPlayed: pctPlayed,
                bye: bye,
                opponent: game?.opponent ?? "",
                isHome: game?.isHome ?? false,
                gameStatus: game?.statusText ?? "",
                gameTime: game?.kickoff,
                score: game?.score,
                opponentScore: game?.opponentScore,
                slot: "",
                currentSlot: ""
            )
        }
    }

    /// Greedy best-ball lineup: walk the slots in league order and give each
    /// one the highest-ranked unassigned eligible player. With `by` set to
    /// `.optimistic` this is the projected lineup; `.points` reproduces the
    /// current Sleeper lineup.
    public static func assignSlots(
        _ players: [RosterPlayer],
        slots: [Slot],
        by keyPath: KeyPath<RosterPlayer, Double>
    ) -> [String: String] {
        let ordered = players.sorted {
            let lhs = $0[keyPath: keyPath]
            let rhs = $1[keyPath: keyPath]
            if lhs == rhs { return $0.id < $1.id }
            return lhs > rhs
        }
        var remaining = ordered
        var assignments: [String: String] = [:]
        for slot in slots {
            guard let index = remaining.firstIndex(where: { slot.eligible.contains($0.position) }) else {
                continue
            }
            assignments[remaining[index].id] = slot.label
            remaining.remove(at: index)
        }
        return assignments
    }

    /// Returns players with both their best-ball slot and their current slot
    /// assigned, ordered for display: starters by slot order, then bench.
    public static func lineup(
        _ players: [RosterPlayer],
        rosterPositions: [String]
    ) -> [RosterPlayer] {
        let slotList = LineupSlots.slots(for: rosterPositions)
        let projected = assignSlots(players, slots: slotList, by: \.optimistic)
        let current = assignSlots(players, slots: slotList, by: \.points)
        let fallback = slotList.first(where: \.isBench)?.label ?? "BN1"

        var assigned = players.map { player in
            player.withSlots(
                slot: projected[player.id] ?? fallback,
                currentSlot: current[player.id] ?? fallback
            )
        }
        let order = Dictionary(uniqueKeysWithValues: slotList.enumerated().map { ($0.element.label, $0.offset) })
        assigned.sort {
            let lhs = order[$0.slot] ?? Int.max
            let rhs = order[$1.slot] ?? Int.max
            if lhs == rhs {
                if $0.optimistic == $1.optimistic { return $0.id < $1.id }
                return $0.optimistic > $1.optimistic
            }
            return lhs < rhs
        }
        return assigned
    }

    /// Current lineup points and best-ball projection for a team, as shown in
    /// the matchup header.
    public static func totals(for players: [RosterPlayer]) -> (points: Double, projected: Double) {
        var points = 0.0
        var projected = 0.0
        for player in players {
            if !player.currentSlot.hasPrefix("BN") {
                points += player.points
            }
            if !player.slot.hasPrefix("BN") {
                projected += player.optimistic
            }
        }
        return (points, projected)
    }
}
