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

/// The matchup Live Activity: lock screen presentation plus the Dynamic Island
/// layouts.
struct MatchupLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: MatchupActivityAttributes.self) { context in
            LockScreenMatchupView(state: context.state, leagueName: context.attributes.leagueName)
                .activityBackgroundTint(Color(red: 0.07, green: 0.10, blue: 0.18))
                .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    SideScore(
                        name: context.state.teamName,
                        points: context.state.points,
                        projected: context.state.projected,
                        alignment: .leading
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
                    HStack(spacing: 6) {
                        Text("WEEK \(context.state.week)")
                        Text("·")
                        Text(context.state.record)
                        Spacer()
                        Text("proj \(context.state.projected.liveScoreText)")
                    }
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                }
            } compactLeading: {
                Text(context.state.points.liveScoreText)
                    .font(.caption2.weight(.bold))
                    .monospacedDigit()
                    .foregroundStyle(.white)
            } compactTrailing: {
                Text(context.state.opponentPoints?.liveScoreText ?? "–")
                    .font(.caption2.weight(.bold))
                    .monospacedDigit()
                    .foregroundStyle(.white.opacity(0.7))
            } minimal: {
                Text(context.state.points.liveScoreText)
                    .font(.caption2.weight(.bold))
                    .monospacedDigit()
                    .foregroundStyle(.white)
            }
            .keylineTint(Color(red: 0.35, green: 0.65, blue: 0.45))
        }
    }
}

private struct LockScreenMatchupView: View {
    let state: MatchupActivityAttributes.ContentState
    let leagueName: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(leagueName.uppercased())
                    .font(.system(size: 10, weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(.white.opacity(0.55))
                    .lineLimit(1)
                Spacer()
                Text("WEEK \(state.week)")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.white.opacity(0.55))
            }

            HStack(alignment: .top, spacing: 12) {
                SideScore(
                    name: state.teamName,
                    points: state.points,
                    projected: state.projected,
                    alignment: .leading,
                    subtitle: state.record
                )

                Text("vs")
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.4))
                    .padding(.top, 20)

                SideScore(
                    name: state.opponentName ?? "Bye",
                    points: state.opponentPoints,
                    projected: state.opponentProjected,
                    alignment: .trailing
                )
            }

            Text("Updated \(state.updated.formatted(.dateTime.hour().minute()))")
                .font(.system(size: 9))
                .foregroundStyle(.white.opacity(0.4))
        }
        .padding(14)
    }
}

private struct SideScore: View {
    let name: String
    let points: Double?
    let projected: Double?
    var alignment: HorizontalAlignment = .leading
    var subtitle: String?

    var body: some View {
        VStack(alignment: alignment, spacing: 1) {
            Text(name)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .lineLimit(1)
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
