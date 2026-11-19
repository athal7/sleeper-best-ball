import ActivityKit
import Foundation
import BestBallKit

/// Keeps one Live Activity per league in sync with the user's matchup for the
/// current week. Updates happen from the app's own refresh, so no push server is
/// involved.
@MainActor
final class LiveActivityController {
    /// One league's matchup for the activity to show.
    struct TrackedMatchup: Sendable {
        let leagueID: String
        let leagueName: String
        let snapshot: WidgetSnapshot
    }

    /// The system only keeps a handful of concurrent Live Activities alive, so
    /// tracking is capped at the first few leagues rather than silently failing.
    static let maxActivities = 5

    static let shared = LiveActivityController()

    private init() {}

    var isAuthorized: Bool { ActivityAuthorizationInfo().areActivitiesEnabled }
    var isTracking: Bool { !Activity<MatchupActivityAttributes>.activities.isEmpty }
    var trackedLeagueIDs: Set<String> {
        Set(Activity<MatchupActivityAttributes>.activities.map(\.attributes.leagueID))
    }

    /// Starts an activity for each matchup that doesn't have one, refreshes the
    /// ones that do, and ends activities for leagues that dropped out (a week
    /// ending, a league being swapped).
    func sync(_ matchups: [TrackedMatchup]) async {
        guard isAuthorized else { return }

        for matchup in matchups {
            let content = ActivityContent(
                state: matchup.snapshot.contentState,
                staleDate: staleDate(matchup.snapshot)
            )
            if let existing = activity(for: matchup.leagueID) {
                await existing.update(content)
            } else if Activity<MatchupActivityAttributes>.activities.count < Self.maxActivities {
                do {
                    _ = try Activity.request(
                        attributes: MatchupActivityAttributes(
                            leagueID: matchup.leagueID,
                            leagueName: matchup.leagueName
                        ),
                        content: content,
                        pushType: nil
                    )
                } catch {
                    // Nothing else would report this: the card would just never
                    // appear, which is indistinguishable from a toggle that does
                    // nothing.
                    print("Live Activity request failed for \(matchup.leagueID): \(error)")
                }
            }
        }

        let keep = Set(matchups.map(\.leagueID))
        for activity in Activity<MatchupActivityAttributes>.activities
        where !keep.contains(activity.attributes.leagueID) {
            await activity.end(nil, dismissalPolicy: .immediate)
        }
    }

    func end() async {
        for activity in Activity<MatchupActivityAttributes>.activities {
            await activity.end(nil, dismissalPolicy: .immediate)
        }
    }

    private func activity(for leagueID: String) -> Activity<MatchupActivityAttributes>? {
        Activity<MatchupActivityAttributes>.activities
            .first { $0.attributes.leagueID == leagueID }
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
