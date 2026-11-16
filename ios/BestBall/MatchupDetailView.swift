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
                        TeamScoreboard(team: myTeam, alignment: .leading)
                    }

                    Text("vs")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.tertiary)
                        .padding(.top, 32)

                    if let opponent {
                        TeamScoreboard(team: opponent, alignment: .trailing)
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
        .navigationTitle("Week \(week.week)")
        .navigationBarTitleDisplayMode(.inline)
    }

    /// Both teams' players in parallel columns so you can read the matchup across
    /// the screen instead of scrolling two stacked lists.
    private func sideBySide(_ players: (TeamScore) -> [RosterPlayer]) -> some View {
        HStack(alignment: .top, spacing: 12) {
            playerColumn(team: myTeam, players: players, trailing: false)
            Divider()
            playerColumn(team: opponent, players: players, trailing: true)
        }
    }

    @ViewBuilder
    private func playerColumn(
        team: TeamScore?,
        players: (TeamScore) -> [RosterPlayer],
        trailing: Bool
    ) -> some View {
        VStack(alignment: trailing ? .trailing : .leading, spacing: 6) {
            if let team {
                ForEach(players(team)) { player in
                    PlayerCell(player: player, trailing: trailing)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: trailing ? .trailing : .leading)
    }
}

/// One player in a side-by-side column: name and live points on the same line,
/// with position/team underneath so the row stays one line tall on a phone.
private struct PlayerCell: View {
    let player: RosterPlayer
    let trailing: Bool

    var body: some View {
        VStack(alignment: trailing ? .trailing : .leading, spacing: 1) {
            HStack(spacing: 4) {
                if trailing {
                    points
                    name
                } else {
                    name
                    Spacer(minLength: 2)
                    points
                }
            }

            Text(player.infoText)
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .opacity(player.isBench ? 0.6 : 1)
    }

    private var name: some View {
        Text(player.name)
            .font(.caption.weight(.medium))
            .lineLimit(1)
    }

    private var points: some View {
        Text(player.pointsText)
            .font(.caption.monospacedDigit().weight(.semibold))
            .foregroundStyle(player.isLive ? Color.green : Color.primary)
    }
}
