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

struct TeamRow: View {
    let team: TeamScore

    var body: some View {
        HStack(spacing: 12) {
            AvatarView(team: team)
            VStack(alignment: .leading, spacing: 2) {
                Text(team.name)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Text("\(team.record) · #\(team.rank)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 2) {
                Text(team.points.scoreText)
                    .font(.headline.monospacedDigit())
                Text("proj \(team.projected.scoreText)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
    }
}

struct MatchupCard: View {
    let matchup: MatchupScore
    let userRosterID: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if matchup.contains(rosterID: userRosterID) {
                Text("YOUR MATCHUP")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.tint)
            }
            ForEach(matchup.teams) { team in
                TeamRow(team: team)
            }
        }
        .padding(.vertical, 4)
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
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                AvatarView(team: team, size: 28)
                Text(team.name)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
            }
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(team.projected.scoreText)
                    .font(.system(size: 34, weight: .bold, design: .rounded).monospacedDigit())
                Text("proj")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text("\(team.points.scoreText) pts · \(team.playedCounts)")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
