import SwiftUI
import BestBallKit

extension Double {
    var scoreText: String { String(format: "%.1f", self) }
}

struct LeagueRow: View {
    let league: LeagueSummary

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(league.name)
                    .font(.body.weight(.medium))
                    .foregroundStyle(.primary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.tertiary)
        }
        .contentShape(Rectangle())
        .padding(.vertical, 2)
    }

    private var subtitle: String {
        var parts: [String] = []
        if !league.season.isEmpty { parts.append(league.season) }
        if let teams = league.totalRosters { parts.append("\(teams) teams") }
        let status: String
        switch league.status {
        case "in_season": status = "In season"
        case "drafting": status = "Drafting"
        case "pre_draft": status = "Pre-draft"
        case "complete": status = "Complete"
        default: status = league.status.capitalized
        }
        parts.append(status)
        return parts.joined(separator: " · ")
    }
}

struct AvatarView: View {
    let team: TeamScore
    var size: CGFloat = 36

    var body: some View {
        Group {
            if let url = team.avatarURL {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    initials
                }
            } else {
                initials
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .overlay(Circle().strokeBorder(.quaternary, lineWidth: 1))
    }

    private var initials: some View {
        ZStack {
            Color(uiColor: .secondarySystemBackground)
            Text(initialsText)
                .font(.system(size: size * 0.34, weight: .bold, design: .rounded))
                .foregroundStyle(.secondary)
        }
    }

    private var initialsText: String {
        let letters = team.name
            .split(separator: " ")
            .prefix(2)
            .compactMap { $0.first }
        return letters.isEmpty ? "?" : String(letters).uppercased()
    }
}

struct MatchupCard: View {
    let matchup: MatchupScore
    let userRosterID: Int?

    private var isUserMatchup: Bool { matchup.contains(rosterID: userRosterID) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if isUserMatchup {
                Label("YOUR MATCHUP", systemImage: "flame.fill")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.tint)
            }

            HStack(alignment: .top, spacing: 8) {
                if let home = matchup.teams.first {
                    MatchupSide(team: home, isUser: home.id == userRosterID)
                }

                Text("vs")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.tertiary)
                    .padding(.top, 14)

                if matchup.teams.count > 1 {
                    let away = matchup.teams[1]
                    MatchupSide(team: away, isUser: away.id == userRosterID)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

/// One half of a matchup card: team identity on top, then the points that
/// actually matter, with the projection as supporting detail.
private struct MatchupSide: View {
    let team: TeamScore
    let isUser: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                AvatarView(team: team, size: 22)
                Text(team.name)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
            }

            Text(team.points.scoreText)
                .font(.system(.title2, design: .rounded).weight(.bold).monospacedDigit())
                .foregroundStyle(isUser ? Color.accentColor : Color.primary)

            Text("proj \(team.projected.scoreText)")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct SlotBadge: View {
    let slot: String

    var body: some View {
        Text(shortLabel)
            .font(.system(.caption2, design: .monospaced).weight(.bold))
            .foregroundStyle(.secondary)
            .frame(width: 48, alignment: .leading)
    }

    private var shortLabel: String {
        slot
            .replacingOccurrences(of: "SUPER_FLEX", with: "SFLEX")
    }
}

struct PlayerRow: View {
    let player: RosterPlayer

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            SlotBadge(slot: player.slot)
            VStack(alignment: .leading, spacing: 2) {
                Text(player.name)
                    .font(.subheadline)
                    .lineLimit(1)
                Text(player.infoText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(player.statusText)
                    .font(.caption2)
                    .foregroundStyle(statusColor)
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 2) {
                Text(player.pointsText)
                    .font(.subheadline.monospacedDigit().weight(.semibold))
                Text(player.projectionText)
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .opacity(player.isBench ? 0.6 : 1)
        .padding(.vertical, 1)
    }

    private var statusColor: Color {
        if player.bye { return .orange }
        if player.isLive { return .green }
        if player.isFinal { return .secondary }
        return .secondary
    }
}

struct TeamScoreboard: View {
    let team: TeamScore

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                AvatarView(team: team, size: 26)
                Text(team.name)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
            }

            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(team.points.scoreText)
                    .font(.system(size: 32, weight: .bold, design: .rounded).monospacedDigit())
                Text("pts")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.secondary)
            }

            Text("proj \(team.projected.scoreText)")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)

            Text("\(team.record) · #\(team.rank)")
                .font(.caption2)
                .foregroundStyle(.tertiary)

            Text(team.playedCounts)
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
