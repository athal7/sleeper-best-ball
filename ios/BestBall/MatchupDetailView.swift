import SwiftUI
import BestBallKit

/// Mirrors the Streamlit matchup view: both teams' players sit in the same row
/// for each lineup slot, with the slot label between them, so you compare QB to
/// QB instead of reading two stacked lists.
struct MatchupDetailView: View {
    let matchup: MatchupScore
    let week: LeagueWeek

    private var myTeam: TeamScore? {
        matchup.teams.first { $0.id == week.userRosterID } ?? matchup.teams.first
    }

    private var opponent: TeamScore? {
        matchup.teams.first { $0.id != myTeam?.id }
    }

    /// Every slot either team fills, in the order the league scores them. The
    /// roster arrives sorted by slot, so the first team's order carries over and
    /// anything only the other team has lands at the end.
    private var slotOrder: [String] {
        var seen: Set<String> = []
        return matchup.teams
            .flatMap { $0.players.map(\.slot) }
            .filter { seen.insert($0).inserted }
    }

    private var starterSlots: [String] { slotOrder.filter { !$0.hasPrefix("BN") } }
    private var benchSlots: [String] { slotOrder.filter { $0.hasPrefix("BN") } }

    var body: some View {
        List {
            Section {
                HStack(alignment: .top, spacing: 10) {
                    if let myTeam {
                        TeamScoreboard(team: myTeam, isUser: myTeam.id == week.userRosterID)
                    }

                    Text("vs")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.tertiary)
                        .padding(.top, 30)

                    if let opponent {
                        TeamScoreboard(team: opponent, isUser: opponent.id == week.userRosterID)
                    }
                }
                .padding(.vertical, 6)
            }

            Section("Starters") {
                rows(for: starterSlots)
            }

            if !benchSlots.isEmpty {
                Section {
                    DisclosureGroup {
                        rows(for: benchSlots)
                    } label: {
                        Text("Bench (\(benchSlots.count))")
                            .font(.subheadline.weight(.medium))
                    }
                }
            }

            Section {
                Text("Each row is one lineup slot. Best-ball rules put your highest optimistic projection in each slot first, so the names here are who scores for each team — bench points don't count.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle(week.leagueName)
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder
    private func rows(for slots: [String]) -> some View {
        ForEach(slots, id: \.self) { slot in
            SlotComparisonRow(
                slot: slot,
                left: player(in: slot, on: myTeam),
                right: player(in: slot, on: opponent)
            )
            .listRowInsets(EdgeInsets(top: 3, leading: 12, bottom: 3, trailing: 12))
        }
    }

    private func player(in slot: String, on team: TeamScore?) -> RosterPlayer? {
        team?.players.first { $0.slot == slot }
    }
}

/// One slot across both teams: their player on each side, the slot name in the
/// middle. An empty side means that team has nobody in that slot.
private struct SlotComparisonRow: View {
    let slot: String
    let left: RosterPlayer?
    let right: RosterPlayer?

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            MatchupPlayerCell(player: left)

            SlotBadge(slot: slot)
                .frame(width: 34, alignment: .center)

            MatchupPlayerCell(player: right)
        }
        .padding(.vertical, 2)
    }
}

/// Name and points on one line, position/team and projection below, game status
/// last — the same three lines the Streamlit table gives each player.
private struct MatchupPlayerCell: View {
    let player: RosterPlayer?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if let player {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    PlayerNameButton(player: PlayerLink(player),
                                     font: .caption, weight: .medium)
                    Spacer(minLength: 2)
                    Text(player.pointsText)
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(player.isLive ? Color.green : Color.primary)
                }

                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(player.infoText)
                        .lineLimit(1)
                    Spacer(minLength: 2)
                    Text(player.projectionText)
                        .monospacedDigit()
                        .lineLimit(1)
                }
                .font(.system(size: 9))
                .foregroundStyle(.secondary)

                Text(player.statusText)
                    .font(.system(size: 9))
                    .italic()
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            } else {
                Text("—")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opacity(player?.isBench == true ? 0.65 : 1)
    }
}
