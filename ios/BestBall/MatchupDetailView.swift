import SwiftUI
import BestBallKit

struct MatchupDetailView: View {
    let matchup: MatchupScore
    let week: LeagueWeek

    private var myTeam: TeamScore? {
        matchup.teams.first { $0.id == week.userRosterID } ?? matchup.teams.first
    }

    private var opponent: TeamScore? {
        matchup.teams.first { $0.id != myTeam?.id }
    }

    private var bench: [RosterPlayer] {
        matchup.teams.flatMap { $0.players.filter(\.isBench) }
    }

    var body: some View {
        List {
            Section {
                HStack(alignment: .top, spacing: 10) {
                    if let myTeam {
                        TeamScoreboard(team: myTeam)
                    }

                    Text("vs")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.tertiary)
                        .padding(.top, 32)

                    if let opponent {
                        TeamScoreboard(team: opponent)
                    }
                }
                .padding(.vertical, 6)
            }

            Section {
                sideBySide { $0.players.filter { !$0.isBench } }
            } header: {
                Text("Starters")
            }

            if !bench.isEmpty {
                Section {
                    DisclosureGroup {
                        sideBySide { $0.players.filter(\.isBench) }
                    } label: {
                        Text("Bench (\(bench.count))")
                            .font(.subheadline.weight(.medium))
                    }
                }
            }

            Section {
                Text("Starters are chosen by best-ball rules: the highest optimistic projection fills each slot first. Bench points don't count.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle(week.leagueName)
        .navigationBarTitleDisplayMode(.inline)
    }

    /// Both teams' players in parallel columns so you can read the matchup across
    /// the screen instead of scrolling two stacked lists. Both columns are
    /// left-aligned so the numbers line up.
    private func sideBySide(_ players: (TeamScore) -> [RosterPlayer]) -> some View {
        HStack(alignment: .top, spacing: 12) {
            playerColumn(team: myTeam, players: players)
            Divider()
            playerColumn(team: opponent, players: players)
        }
    }

    @ViewBuilder
    private func playerColumn(team: TeamScore?, players: (TeamScore) -> [RosterPlayer]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if let team {
                ForEach(players(team)) { player in
                    PlayerCell(player: player)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// One player in a side-by-side column: name and live points on the same line,
/// with position/team underneath so the row stays one line tall on a phone.
private struct PlayerCell: View {
    let player: RosterPlayer

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            HStack(spacing: 4) {
                Text(player.name)
                    .font(.caption.weight(.medium))
                    .lineLimit(1)
                Spacer(minLength: 2)
                Text(player.pointsText)
                    .font(.caption.monospacedDigit().weight(.semibold))
                    .foregroundStyle(player.isLive ? Color.green : Color.primary)
            }

            HStack(spacing: 4) {
                Text(player.slot)
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .frame(minWidth: 22, alignment: .leading)
                Text(player.infoText)
                    .font(.system(size: 9))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .opacity(player.isBench ? 0.6 : 1)
    }
}
