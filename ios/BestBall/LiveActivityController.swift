import ActivityKit
import Foundation
import BestBallKit

/// Keeps one Live Activity in sync with the user's matchup for the week the app
/// is showing. Updates happen from the app's own refresh, so no push server is
/// involved.
@MainActor
final class LiveActivityController {
    static let shared = LiveActivityController()

    private init() {}

    var isAuthorized: Bool { ActivityAuthorizationInfo().areActivitiesEnabled }
    var isTracking: Bool { !Activity<MatchupActivityAttributes>.activities.isEmpty }

    /// Starts tracking the matchup, or refreshes the activity that's already
    /// running. A no-op when the user has Live Activities turned off for the app.
    func sync(_ snapshot: WidgetSnapshot) async {
        guard isAuthorized else { return }
        let content = ActivityContent(state: snapshot.contentState, staleDate: staleDate(snapshot))
        if let activity = Activity<MatchupActivityAttributes>.activities.first {
            await activity.update(content)
            return
        }
        _ = try? Activity.request(
            attributes: MatchupActivityAttributes(leagueName: snapshot.leagueName),
            content: content,
            pushType: nil
        )
    }

    func end() async {
        for activity in Activity<MatchupActivityAttributes>.activities {
            await activity.end(nil, dismissalPolicy: .immediate)
        }
    }

    /// The scores go stale once the week's games are done; the system dims the
    /// activity instead of showing numbers that look current.
    private func staleDate(_ snapshot: WidgetSnapshot) -> Date {
        snapshot.updated.addingTimeInterval(60 * 60)
    }
}

extension WidgetSnapshot {
    var contentState: MatchupActivityAttributes.ContentState {
        MatchupActivityAttributes.ContentState(
            week: week,
            teamName: teamName,
            record: record,
            projected: projected,
            points: points,
            opponentName: opponentName,
            opponentProjected: opponentProjected,
            opponentPoints: opponentPoints,
            updated: updated
        )
    }
}
