import ActivityKit
import SwiftUI
import WidgetKit

private extension Double {
    var liveScoreText: String { String(format: "%.1f", self) }
}

private let fieldGradient = LinearGradient(
    colors: [Color(red: 0.07, green: 0.10, blue: 0.18),
             Color(red: 0.12, green: 0.17, blue: 0.28)],
    startPoint: .topLeading,
    endPoint: .bottomTrailing
)

private let accent = Color(red: 0.35, green: 0.80, blue: 0.55)
private let dim = Color.white.opacity(0.5)

/// The matchup Live Activity: lock screen presentation plus the Dynamic Island
/// layouts. Every layout answers three things — which league, which teams, and
/// whose side is yours — and shows how old the numbers are.
struct MatchupLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: MatchupActivityAttributes.self) { context in
            LockScreenMatchupView(
                state: context.state,
                leagueName: context.attributes.leagueName
            )
            .activityBackgroundTint(Color(red: 0.07, green: 0.10, blue: 0.18))
            .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    SideScore(
                        name: context.state.teamName,
                        points: context.state.points,
                        projected: context.state.projected,
                        alignment: .leading,
                        isYou: true
                    )
                }
                DynamicIslandExpandedRegion(.trailing) {
                    SideScore(
                        name: context.state.opponentName ?? "Bye",
                        points: context.state.opponentPoints,
                        projected: context.state.opponentProjected,
                        alignment: .trailing
                    )
                }
                DynamicIslandExpandedRegion(.bottom) {
                    HStack(spacing: 5) {
                        Image(systemName: "football.fill")
                            .font(.system(size: 8))
                        Text(context.attributes.leagueName.uppercased())
                            .lineLimit(1)
                        Text("·")
                        Text("WK \(context.state.week)")
                        Spacer(minLength: 4)
                        RefreshedLabel(updated: context.state.updated, compact: true)
                    }
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(dim)
                }
            } compactLeading: {
                // A football plus your score: the icon says what the activity is,
                // and the leading side is always you.
                HStack(spacing: 2) {
                    Image(systemName: "football.fill")
                        .font(.system(size: 9))
                        .foregroundStyle(accent)
                    Text(context.state.points.liveScoreText)
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.white)
                }
            } compactTrailing: {
                Text(context.state.opponentPoints?.liveScoreText ?? "–")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(dim)
            } minimal: {
                // Too small for names, so it reads as a scoreline instead of a
                // stray number: yours bright, theirs dimmed, separated by a dash.
                (
                    Text(context.state.points.liveScoreText)
                        .foregroundStyle(.white)
                    + Text("–").foregroundStyle(Color.white.opacity(0.35))
                    + Text(context.state.opponentPoints?.liveScoreText ?? "–")
                        .foregroundStyle(dim)
                )
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            }
            .keylineTint(accent)
        }
    }
}

private struct LockScreenMatchupView: View {
    let state: MatchupActivityAttributes.ContentState
    let leagueName: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 4) {
                Image(systemName: "football.fill")
                    .font(.system(size: 9))
                    .foregroundStyle(accent)
                Text(leagueName)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.white.opacity(0.75))
                    .lineLimit(1)
                Spacer(minLength: 6)
                Text("WEEK \(state.week)")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.white.opacity(0.45))
            }

            HStack(alignment: .top, spacing: 12) {
                SideScore(
                    name: state.teamName,
                    points: state.points,
                    projected: state.projected,
                    alignment: .leading,
                    subtitle: state.record,
                    isYou: true
                )

                Text("vs")
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.35))
                    .padding(.top, 22)

                SideScore(
                    name: state.opponentName ?? "Bye",
                    points: state.opponentPoints,
                    projected: state.opponentProjected,
                    alignment: .trailing
                )
            }

            RefreshedLabel(updated: state.updated)
        }
        .padding(14)
    }
}

/// "Updated 3 min ago" — the relative style keeps counting without an update.
private struct RefreshedLabel: View {
    let updated: Date
    var compact = false

    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: "arrow.triangle.2.circlepath")
                .font(.system(size: compact ? 8 : 8.5))
            Text("Updated")
            Text(updated, style: .relative)
            Text("ago")
        }
        .font(.system(size: compact ? 9 : 9.5))
        .foregroundStyle(.white.opacity(compact ? 0.45 : 0.4))
        .lineLimit(1)
    }
}

private struct SideScore: View {
    let name: String
    let points: Double?
    let projected: Double?
    var alignment: HorizontalAlignment = .leading
    var subtitle: String?
    var isYou = false

    var body: some View {
        VStack(alignment: alignment, spacing: 1) {
            HStack(spacing: 3) {
                if alignment == .trailing, isYou { YouTag() }
                Text(name)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                if alignment != .trailing, isYou { YouTag() }
            }
            if let subtitle {
                Text(subtitle)
                    .font(.system(size: 9))
                    .foregroundStyle(.white.opacity(0.5))
            }
            Text(points?.liveScoreText ?? "–")
                .font(.system(size: 24, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.white)
            if let projected {
                Text("proj \(projected.liveScoreText)")
                    .font(.system(size: 9))
                    .foregroundStyle(.white.opacity(0.5))
            }
        }
        .frame(maxWidth: .infinity, alignment: alignment == .trailing ? .trailing : .leading)
    }
}

private struct YouTag: View {
    var body: some View {
        Text("YOU")
            .font(.system(size: 7, weight: .heavy))
            .foregroundStyle(accent)
            .padding(.horizontal, 3)
            .padding(.vertical, 1)
            .background(Capsule().fill(accent.opacity(0.18)))
    }
}
