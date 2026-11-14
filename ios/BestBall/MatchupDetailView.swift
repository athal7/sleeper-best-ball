import SwiftUI
import BestBallKit

struct MatchupDetailView: View {
    let matchup: MatchupScore
    let week: LeagueWeek

    var body: some View {
        List {
            Section {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(matchup.teams) { team in
                        TeamScoreboard(team: team)
                        if team.id != matchup.teams.last?.id {
                            Text("vs")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .padding(.top, 32)
                        }
                    }
                }
                .padding(.vertical, 6)
            }

            ForEach(matchup.teams) { team in
                teamSection(team)
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

    private func teamSection(_ team: TeamScore) -> some View {
        let starters = team.players.filter { !$0.isBench }
        let bench = team.players.filter(\.isBench)

        return Section {
            ForEach(starters) { player in
                PlayerRow(player: player)
            }
            if !bench.isEmpty {
                DisclosureGroup {
                    ForEach(bench) { player in
                        PlayerRow(player: player)
                    }
                } label: {
                    Text("Bench (\(bench.count))")
                        .font(.subheadline.weight(.medium))
                }
            }
        } header: {
            HStack {
                Text(team.name)
                Spacer()
                Text("proj \(team.projected.scoreText)")
                    .monospacedDigit()
            }
            .font(.caption)
        }
    }
}
