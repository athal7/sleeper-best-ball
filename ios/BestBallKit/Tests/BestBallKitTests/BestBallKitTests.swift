import Foundation
import Testing
@testable import BestBallKit

@Suite struct ScoringTests {
    @Test func pointsMultiplyMatchingStatsOnly() {
        let stats: [String: Double] = [
            "pass_yd": 250,
            "pass_td": 2,
            "pass_int": 1,
            "rec": 8,
        ]
        let scoring: [String: Double] = [
            "pass_yd": 0.04,
            "pass_td": 4,
            "pass_int": -2,
            "rec": 1,
            "rush_yd": 0.1,
        ]
        // Missing stats count as zero; scoring keys absent from stats are ignored.
        expectClose(Scoring.points(stats: stats, scoring: scoring), 24)
    }

    @Test func statLineDecodingIgnoresNonNumericValues() throws {
        let json = """
        {"4034": {"rec": 8, "rec_yd": 82.5, "team": "MIN", "injury": null, "flag": true}}
        """.data(using: .utf8)!
        let table = Scoring.table(
            from: try JSONDecoder().decode([String: StatLine].self, from: json)
        )
        #expect(table["4034"]?["rec"] == 8)
        #expect(table["4034"]?["rec_yd"] == 82.5)
        #expect(table["4034"]?["team"] == nil)
        #expect(table["4034"]?["flag"] == nil)
    }
}

@Suite struct SlotsTests {
    @Test func slotsExpandInLeagueOrder() {
        let positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX",
                         "SUPER_FLEX", "K", "DEF", "BN", "BN", "BN", "BN"]
        let slots = LineupSlots.slots(for: positions)
        #expect(slots.map(\.label) == ["QB1", "RB1", "RB2", "WR1", "WR2", "WR3",
                                      "TE1", "FLEX1", "SUPER_FLEX1", "K1", "DEF1",
                                      "BN1", "BN2", "BN3", "BN4"])
    }

    @Test func slotsIgnoreUnsupportedPositions() {
        let slots = LineupSlots.slots(for: ["QB", "IDP_FLEX", "BN"])
        #expect(slots.map(\.label) == ["QB1", "BN1"])
    }

    @Test func flexEligibility() {
        let slots = LineupSlots.slots(for: ["FLEX", "SUPER_FLEX", "BN"])
        #expect(slots[0].eligible == ["RB", "WR", "TE"])
        #expect(slots[1].eligible == ["QB", "RB", "WR", "TE"])
    }
}

@Suite struct LineupTests {
    @Test func bestBallLineupStartsTwoQuarterbacksInSuperflex() {
        let players = [
            makePlayer("qb1", position: "QB", points: 10, optimistic: 25),
            makePlayer("qb2", position: "QB", points: 5, optimistic: 20),
            makePlayer("rb1", position: "RB", points: 9, optimistic: 15),
            makePlayer("wr1", position: "WR", points: 8, optimistic: 14),
            makePlayer("te1", position: "TE", points: 7, optimistic: 13),
            makePlayer("k1", position: "K", points: 6, optimistic: 8),
            makePlayer("def1", position: "DEF", points: 4, optimistic: 7),
        ]
        let positions = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "K", "DEF", "BN", "BN"]
        let lineup = BestBallEngine.lineup(players, rosterPositions: positions)
        let slots = Dictionary(uniqueKeysWithValues: lineup.map { ($0.id, $0.slot) })

        #expect(slots["qb1"] == "QB1")
        #expect(slots["qb2"] == "SUPER_FLEX1")
        #expect(slots["rb1"] == "RB1")
        #expect(slots["wr1"] == "WR1")
        #expect(slots["te1"] == "TE1")
        #expect(slots["k1"] == "K1")
        #expect(slots["def1"] == "DEF1")

        let totals = BestBallEngine.totals(for: lineup)
        expectClose(totals.projected, 102)
        expectClose(totals.points, 49)
    }

    @Test func benchReceivesLowestOptimisticPlayers() {
        let players = [
            makePlayer("wr1", position: "WR", points: 0, optimistic: 20),
            makePlayer("wr2", position: "WR", points: 0, optimistic: 10),
            makePlayer("wr3", position: "WR", points: 0, optimistic: 5),
            makePlayer("rb1", position: "RB", points: 0, optimistic: 12),
        ]
        let lineup = BestBallEngine.lineup(players, rosterPositions: ["WR", "FLEX", "BN", "BN"])
        let slots = Dictionary(uniqueKeysWithValues: lineup.map { ($0.id, $0.slot) })

        #expect(slots["wr1"] == "WR1")
        #expect(slots["rb1"] == "FLEX1")
        #expect(slots["wr2"] == "BN1")
        #expect(slots["wr3"] == "BN2")
        expectClose(BestBallEngine.totals(for: lineup).projected, 32)
        #expect(lineup.first?.id == "wr1")
    }

    @Test func currentLineupUsesPointsNotProjection() {
        let players = [
            makePlayer("a", position: "RB", points: 20, optimistic: 21),
            makePlayer("b", position: "RB", points: 2, optimistic: 30),
        ]
        let lineup = BestBallEngine.lineup(players, rosterPositions: ["RB", "BN"])
        let byID = Dictionary(uniqueKeysWithValues: lineup.map { ($0.id, $0) })

        #expect(byID["b"]?.slot == "RB1")
        #expect(byID["a"]?.slot == "BN1")
        #expect(byID["a"]?.currentSlot == "RB1")
        #expect(byID["b"]?.currentSlot == "BN1")
        expectClose(BestBallEngine.totals(for: lineup).points, 20)
        expectClose(BestBallEngine.totals(for: lineup).projected, 30)
    }
}

@Suite struct EngineTests {
    @Test func optimisticProjectionUsesRemainingGameTime() {
        let directory = [
            "p1": SleeperPlayer(playerID: "p1", firstName: "Justin", lastName: "Jefferson",
                                position: "WR", team: "MIN", injuryStatus: "Questionable"),
            "p2": SleeperPlayer(playerID: "p2", firstName: "Bijan", lastName: "Robinson",
                                position: "RB", team: "ATL", injuryStatus: nil),
            "p3": SleeperPlayer(playerID: "p3", firstName: "No", lastName: "Team",
                                position: "WR", team: "", injuryStatus: nil),
        ]
        let games = [
            "MIN": TeamGame(team: "MIN", opponent: "GB", quarter: 2, clock: 450,
                            statusText: "Q2 7:30", isHome: true, score: 10,
                            opponentScore: 7, kickoff: nil),
        ]
        let stats: StatTable = [
            "p1": ["rec": 4, "rec_yd": 50],
            "p2": ["rush_yd": 40],
        ]
        let projections: StatTable = [
            "p1": ["rec": 8, "rec_yd": 95],
            "p2": ["rush_yd": 70],
        ]
        let scoring: [String: Double] = ["rec": 1, "rec_yd": 0.1, "rush_yd": 0.1]

        let players = BestBallEngine.players(
            playerIDs: ["p1", "p2", "p3", "missing"],
            directory: directory,
            stats: stats,
            projections: projections,
            scoring: scoring,
            games: games,
            gamesAvailable: true
        )
        let byID = Dictionary(uniqueKeysWithValues: players.map { ($0.id, $0) })

        #expect(players.count == 3)
        expectClose(byID["p1"]?.points ?? 0, 9)
        expectClose(byID["p1"]?.projection ?? 0, 17.5)
        // Q2 with 450s left means 22.5 of 60 game minutes have elapsed.
        expectClose(byID["p1"]?.pctPlayed ?? 0, 0.375)
        expectClose(byID["p1"]?.optimistic ?? 0, 9 + 0.625 * 17.5)
        #expect(byID["p1"]?.statusText == "Q2 7:30 10-7 vs GB")
        #expect(byID["p1"]?.infoText == "WR · MIN (Q)")

        // No game this week means a bye: points so far plus the full projection.
        #expect(byID["p2"]?.bye == true)
        expectClose(byID["p2"]?.optimistic ?? 0, 4 + 7)
        #expect(byID["p2"]?.statusText == "Bye")
        #expect(byID["p3"]?.bye == true)
    }

    @Test func noGamesAvailableDoesNotMarkEveryoneOnBye() {
        let directory = [
            "p1": SleeperPlayer(playerID: "p1", firstName: "A", lastName: "Back",
                                position: "RB", team: "KC", injuryStatus: nil),
        ]
        let players = BestBallEngine.players(
            playerIDs: ["p1"], directory: directory, stats: [:], projections: [:],
            scoring: [:], games: [:], gamesAvailable: false
        )
        #expect(players.first?.bye == false)
        #expect(players.first?.pctPlayed == 0)
    }
}

@Suite struct DecodingTests {
    @Test func leagueDecodingToleratesMissingFields() throws {
        let json = """
        {
          "name": "Best Ball",
          "season": "2026",
          "status": "in_season",
          "scoring_settings": {"rec": 1, "bonus_rec_te": 0.5},
          "roster_positions": ["QB", "RB", "WR", "BN"],
          "settings": {"playoff_week_start": 15, "num_teams": 12}
        }
        """.data(using: .utf8)!
        let league = try JSONDecoder().decode(SleeperLeague.self, from: json)
        #expect(league.name == "Best Ball")
        #expect(league.scoringSettings["bonus_rec_te"] == 0.5)
        #expect(league.settings.playoffWeekStart == 15)
    }

    @Test func leagueSummaryAcceptsNumericLeagueID() throws {
        let json = """
        {"league_id": 12345, "name": "Dynasty", "season": "2026", "status": "complete",
         "total_rosters": 10}
        """.data(using: .utf8)!
        let league = try JSONDecoder().decode(LeagueSummary.self, from: json)
        #expect(league.leagueID == "12345")
        #expect(league.totalRosters == 10)
    }

    @Test func rosterDecodingFlattensSettingsAndMetadata() throws {
        let json = """
        {"roster_id": 3, "owner_id": "u1", "players": ["1", "2"],
         "settings": {"wins": 4, "losses": 2, "fpts": 812.5},
         "metadata": {"team_name": "League Winners"}}
        """.data(using: .utf8)!
        let roster = try JSONDecoder().decode(SleeperRoster.self, from: json)
        #expect(roster.wins == 4)
        #expect(roster.losses == 2)
        #expect(roster.fpts == 812.5)
        #expect(roster.teamName == "League Winners")
        #expect(roster.players == ["1", "2"])
    }

    @Test func playerDirectoryDropsPlayersWithoutPositions() throws {
        let json = """
        {
          "4034": {"first_name": "Justin", "last_name": "Jefferson",
                   "position": "WR", "team": "MIN", "injury_status": "Questionable"},
          "9999": {"first_name": "Team", "last_name": "Defense", "team": "MIN"},
          "8888": {"first_name": "Empty", "last_name": "Position", "position": "", "team": "FA"}
        }
        """.data(using: .utf8)!
        let directory = try SleeperPlayer.decodeDirectory(from: json)
        #expect(directory.count == 1)
        #expect(directory["4034"]?.displayName == "J. Jefferson")
        #expect(directory["4034"]?.injuryStatus == "Questionable")
    }

    @Test func sportStateDefaultWeek() {
        let inSeason = SportState(week: 10, season: "2026", seasonType: "regular",
                                  leagueSeason: "2026", displayWeek: 10)
        #expect(inSeason.defaultWeek == 10)

        let offseason = SportState(week: 0, season: "2026", seasonType: "off",
                                   leagueSeason: "2026", displayWeek: 0)
        #expect(offseason.defaultWeek == 1)
    }

    @Test func gameClockParsingHandlesESPNDateFormats() {
        #expect(SleeperAPI.parseDate("2025-10-03T00:15Z") != nil)
        #expect(SleeperAPI.parseDate("2025-10-03T00:15:00Z") != nil)
        #expect(SleeperAPI.parseDate("2025-10-03T00:15:00.000Z") != nil)
        #expect(SleeperAPI.parseDate(nil) == nil)
        #expect(SleeperAPI.parseDate("not a date") == nil)
    }

    @Test func gamePctPlayedClampsAtFinal() {
        let final = TeamGame(team: "SF", opponent: "LAR", quarter: 5, clock: 0,
                             statusText: "Final/OT", isHome: false, score: 26,
                             opponentScore: 23, kickoff: nil)
        #expect(final.pctPlayed == 1)
        let pregame = TeamGame(team: "SF", opponent: "LAR", quarter: 0, clock: 0,
                               statusText: "8:15 ET", isHome: false, score: 0,
                               opponentScore: 0, kickoff: nil)
        #expect(pregame.pctPlayed == 0)
    }
}

@Suite struct WidgetSnapshotTests {
    @Test func snapshotPicksTheUsersOpponent() {
        let user = makeTeam(rosterID: 1, name: "My Team", projected: 132.4)
        let opponent = makeTeam(rosterID: 2, name: "Rival", projected: 128.9)
        let week = LeagueWeek(
            leagueID: "L1", leagueName: "Best Ball", week: 5, season: 2026,
            matchups: [MatchupScore(matchupID: 1, teams: [user, opponent])],
            userRosterID: 1, updated: Date()
        )
        let snapshot = week.widgetSnapshot()
        #expect(snapshot?.teamName == "My Team")
        #expect(snapshot?.opponentName == "Rival")
        expectClose(snapshot?.projected ?? 0, 132.4)
        expectClose(snapshot?.opponentProjected ?? 0, 128.9)
        #expect(snapshot?.week == 5)
    }

    @Test func snapshotSurvivesEncoding() throws {
        let snapshot = WidgetSnapshot(
            leagueName: "Best Ball", week: 5, teamName: "My Team", record: "4-1",
            rank: 2, projected: 132.4, points: 88.1, opponentName: "Rival",
            opponentProjected: 128.9, opponentPoints: 91, updated: Date()
        )
        let data = try JSONEncoder().encode(snapshot)
        #expect(try JSONDecoder().decode(WidgetSnapshot.self, from: data) == snapshot)
    }
}

// MARK: - Fixtures

private func expectClose(_ lhs: Double, _ rhs: Double, _ tolerance: Double = 1e-9) {
    #expect(abs(lhs - rhs) < tolerance, "\(lhs) is not within \(tolerance) of \(rhs)")
}

private func makePlayer(_ id: String, position: String, points: Double,
                        projection: Double = 0, optimistic: Double,
                        pctPlayed: Double = 0) -> RosterPlayer {
    RosterPlayer(
        id: id, firstName: "First", lastName: id.uppercased(), position: position,
        team: "KC", injuryStatus: nil, points: points, projection: projection,
        optimistic: optimistic, pctPlayed: pctPlayed, bye: false, opponent: "LV",
        isHome: true, gameStatus: "", gameTime: nil, score: nil, opponentScore: nil,
        slot: "", currentSlot: ""
    )
}

private func makeTeam(rosterID: Int, name: String, projected: Double) -> TeamScore {
    TeamScore(
        rosterID: rosterID, name: name, username: "user\(rosterID)", avatar: nil,
        record: "4-1", rank: rosterID, points: 88.1, projected: projected, players: []
    )
}

@Suite struct WaiverTests {
    private let slots = LineupSlots.slots(for: ["QB", "RB", "RB", "WR", "FLEX", "BN"])

    @Test func lineupTotalFillsBestEligiblePlayerPerSlot() {
        let scanner = WaiverScanner()
        let positions = ["qb": "QB", "rb1": "RB", "rb2": "RB", "wr": "WR", "te": "TE"]
        let points = ["qb": 20.0, "rb1": 15.0, "rb2": 12.0, "wr": 18.0, "te": 9.0]
        // QB takes the quarterback, both RBs take the backs, WR takes the receiver,
        // and FLEX takes whatever startable player is left over: the tight end.
        expectClose(scanner.lineupTotal(points, positions, slots), 20 + 15 + 12 + 18 + 9)
    }

    @Test func lineupTotalRewardsUpgradingTheWeakestStarter() {
        let scanner = WaiverScanner()
        let positions = ["qb": "QB", "rb1": "RB", "rb2": "RB"]
        let before = ["qb": 20.0, "rb1": 15.0, "rb2": 8.0]
        var after = before
        after["rb3"] = 14.0
        var afterPositions = positions
        afterPositions["rb3"] = "RB"
        let upgrade = scanner.lineupTotal(after, afterPositions, slots)
            - scanner.lineupTotal(before, positions, slots)
        // The 14-point back starts over the 8-point one, and the displaced back
        // slides into FLEX, so the whole gain counts.
        expectClose(upgrade, 14)
    }

    @Test func lineupTotalIgnoresBenchSlots() {
        let scanner = WaiverScanner()
        let benchOnly = LineupSlots.slots(for: ["BN"])
        let points = ["a": 30.0, "b": 20.0]
        let positions = ["a": "RB", "b": "WR"]
        expectClose(scanner.lineupTotal(points, positions, benchOnly), 0)
    }

    @Test(arguments: [
        (15, 4, 0, 16),
        (15, 6, 0, 17),
        (15, 6, 1, 18),
        (15, 4, 2, 18),
    ])
    func seasonEndWeekIncludesTheChampionship(start: Int, teams: Int, roundType: Int, expected: Int) {
        // Same cases as tests/test_waiver.py.
        let settings = SleeperLeague.Settings(
            playoffWeekStart: start, playoffTeams: teams,
            playoffRoundType: roundType, numTeams: 12
        )
        #expect(WaiverScanner.seasonEndWeek(settings) == expected)
    }

    @Test func seasonEndWeekDefaultsToTheFullSeason() {
        let noPlayoffs = SleeperLeague.Settings(
            playoffWeekStart: 0, playoffTeams: 0, playoffRoundType: 0, numTeams: 12
        )
        #expect(WaiverScanner.seasonEndWeek(noPlayoffs) == 18)
    }
}

@Suite struct TradeTests {
    private let slots = LineupSlots.slots(for: ["RB", "WR"])

    private func asset(_ id: String, _ position: String, _ points: Double) -> TradeAsset {
        TradeAsset(id: id, name: id.uppercased(), position: position, team: "KC", p50: points)
    }

    /// One scored week, so the uplift is plain points per week.
    private func board(my: [TradeAsset], partner: [TradeAsset],
                       weekly: [String: Double]) -> TradeBoard {
        TradeBoard(
            id: "L1", name: "League",
            teams: [
                TradeTeam(id: "1", name: "Your team", assets: my),
                TradeTeam(id: "2", name: "Partner Team", assets: partner),
            ],
            userTeamID: "1", slots: slots, weeks: [1], weights: [1.0],
            weekly: [1: weekly]
        )
    }

    @Test func winWinSwapHelpsBothSides() {
        // Same case as test_compute_trade_recommendations_win_win_trade.
        let board = board(
            my: [asset("wr1", "WR", 20), asset("wr2", "WR", 18)],
            partner: [asset("rb1", "RB", 20), asset("rb2", "RB", 18)],
            weekly: ["wr1": 20, "wr2": 18, "rb1": 20, "rb2": 18]
        )
        let offers = board.analyze(myTeamID: "1", partnerTeamID: "2")
        #expect(offers.count == 4)

        let trade = offers.first { $0.give.map(\.id) == ["wr2"] && $0.receive.map(\.id) == ["rb2"] }
        expectClose(trade?.myUplift ?? 0, 18)
        expectClose(trade?.partnerUplift ?? 0, 18)
    }

    @Test func oneSidedTradeIsExcluded() {
        // Same case as test_compute_trade_recommendations_excludes_one_sided_trade.
        let board = board(
            my: [asset("wr_weak", "WR", 10)],
            partner: [asset("rb_star", "RB", 20), asset("wr_good", "WR", 15)],
            weekly: ["wr_weak": 10, "rb_star": 20, "wr_good": 15]
        )
        #expect(board.analyze(myTeamID: "1", partnerTeamID: "2").isEmpty)
    }

    @Test func positionNeedsFilterBothSides() {
        let board = board(
            my: [asset("wr1", "WR", 20), asset("wr2", "WR", 18)],
            partner: [asset("rb1", "RB", 20), asset("rb2", "RB", 18), asset("wr3", "WR", 12)],
            weekly: ["wr1": 20, "wr2": 18, "rb1": 20, "rb2": 18, "wr3": 12]
        )
        let mine = board.analyze(myTeamID: "1", partnerTeamID: "2", myNeed: "RB")
        #expect(!mine.isEmpty)
        #expect(mine.allSatisfy { $0.receive.allSatisfy { $0.position == "RB" } })

        let theirs = board.analyze(myTeamID: "1", partnerTeamID: "2", partnerNeed: "WR")
        #expect(!theirs.isEmpty)
        #expect(theirs.allSatisfy { $0.give.allSatisfy { $0.position == "WR" } })
    }

    @Test func leagueThresholdRequiresMoreThanOnePointPerWeek() {
        let board = board(
            my: [asset("wr1", "WR", 20), asset("wr2", "WR", 18)],
            partner: [asset("rb1", "RB", 20), asset("rb2", "RB", 18)],
            weekly: ["wr1": 20, "wr2": 18, "rb1": 20, "rb2": 18]
        )
        // The best offers gain 20 a week, and the analyzer's zero threshold is
        // what keeps them; a 19-point bar clears nothing.
        #expect(board.analyze(myTeamID: "1", partnerTeamID: "2", minUplift: 1).count == 4)
        #expect(board.analyze(myTeamID: "1", partnerTeamID: "2", minUplift: 19).isEmpty)
    }

    @Test func packagesPairTheBestPlayersToo() {
        // My spare receivers against a partner who only has backs: two-for-two
        // deals exist alongside the straight swaps.
        let board = board(
            my: [asset("wr1", "WR", 20), asset("wr2", "WR", 18), asset("wr3", "WR", 16)],
            partner: [asset("rb1", "RB", 20), asset("rb2", "RB", 18), asset("rb3", "RB", 16)],
            weekly: ["wr1": 20, "wr2": 18, "wr3": 16,
                     "rb1": 20, "rb2": 18, "rb3": 16]
        )
        let offers = board.analyze(myTeamID: "1", partnerTeamID: "2", minUplift: 1)
        #expect(offers.contains { $0.give.count == 2 && $0.receive.count == 2 })
    }

    @Test func rosterSlotsMirrorTheUsersOwnRoster() {
        // The Streamlit app falls back to DraftSettings.from_actual_roster, so the
        // slot set is one slot per player on the user's roster, eligible only for
        // that player's own position — no flex, no bench.
        let assets = [
            asset("qb1", "QB", 20), asset("qb2", "QB", 18),
            asset("rb1", "RB", 15), asset("wr1", "WR", 12),
        ]
        let slots = TradeBoard.rosterSlots(for: assets)
        #expect(slots.count == 4)
        #expect(slots.filter { $0.position == "QB" }.count == 2)
        #expect(slots.allSatisfy { $0.eligible == [$0.position] })
        #expect(slots.allSatisfy { !$0.isBench })
    }

    @Test func everyRosteredPlayerScoresUnderRosterSlots() {
        // Two receivers against two backs, scored with the web's roster slots:
        // both of my receivers fill a slot, so the swap has to count the second
        // receiver the way the web's bench-less lineup does.
        let mine = [asset("wr1", "WR", 20), asset("wr2", "WR", 18)]
        let theirs = [asset("rb1", "RB", 20), asset("rb2", "RB", 18)]
        let board = TradeBoard(
            id: "L1", name: "League",
            teams: [
                TradeTeam(id: "1", name: "Your team", assets: mine),
                TradeTeam(id: "2", name: "Partner Team", assets: theirs),
            ],
            userTeamID: "1", slots: TradeBoard.rosterSlots(for: mine),
            weeks: [1], weights: [1.0],
            weekly: [1: ["wr1": 20, "wr2": 18, "rb1": 20, "rb2": 18]]
        )
        // My lineup is 20 + 18 = 38 with no back slot at all, so sending a
        // receiver for a back drops my score instead of raising it.
        let offers = board.analyze(myTeamID: "1", partnerTeamID: "2", minUplift: 0)
        #expect(offers.isEmpty)
    }
}
