import Foundation

/// One week of scores across every league an account is in. Shared by the app and
/// by background refresh so both build the same picture from the same requests.
public struct ScoresLoader: Sendable {
    public struct Slice: Sendable {
        public let account: SleeperAccount
        public let leagues: [LeagueSummary]
        public let weeks: [LeagueWeek]
        public let season: Int
        public let week: Int
        public let state: SportState?
    }

    private let service: BestBallService

    public init(service: BestBallService = BestBallService()) {
        self.service = service
    }

    /// Loads the given week (or the week Sleeper considers current) for every
    /// league the account is in, skipped leagues with nothing to show.
    public func load(username: String, season: Int? = nil, week: Int? = nil) async throws -> Slice {
        let state = try? await service.sportState()
        let resolvedSeason = season
            ?? state.flatMap { Int($0.leagueSeason) }
            ?? Calendar.current.component(.year, from: Date())
        let resolvedWeek = week ?? state?.defaultWeek ?? 1

        let lookup = try await service.lookup(username: username, season: resolvedSeason)
        let leagues = lookup.leagues.sorted(by: Self.order)

        let inSeason = leagues.filter { $0.status == "in_season" }
        // Sleeper occasionally returns the same league more than once; scoring it
        // twice would mean two matchups and two Live Activities for one league.
        var seen = Set<String>()
        let plans = (inSeason.isEmpty ? leagues : inSeason)
            .map(\.leagueID)
            .filter { seen.insert($0).inserted }
        let userID = lookup.account.userID
        let targetWeek = resolvedWeek

        let weeks = await withTaskGroup(of: (Int, LeagueWeek?).self) { group in
            for (index, leagueID) in plans.enumerated() {
                group.addTask {
                    let week = try? await service.loadWeek(
                        leagueID: leagueID,
                        week: targetWeek,
                        userID: userID
                    )
                    return (index, week)
                }
            }
            var results: [(Int, LeagueWeek?)] = []
            for await result in group { results.append(result) }
            return results.sorted { $0.0 < $1.0 }.compactMap(\.1)
        }

        return Slice(
            account: lookup.account,
            leagues: leagues,
            weeks: weeks,
            season: resolvedSeason,
            week: targetWeek,
            state: state
        )
    }

    /// Leagues that are currently playing come first, then drafts, then finished ones.
    static func order(_ lhs: LeagueSummary, _ rhs: LeagueSummary) -> Bool {
        let lhsRank = statusRank(lhs.status)
        let rhsRank = statusRank(rhs.status)
        if lhsRank != rhsRank { return lhsRank < rhsRank }
        return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
    }

    private static func statusRank(_ status: String) -> Int {
        switch status {
        case "in_season": return 0
        case "drafting": return 1
        case "pre_draft": return 2
        case "complete": return 3
        default: return 4
        }
    }
}
