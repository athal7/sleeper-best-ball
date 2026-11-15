import ActivityKit
import Foundation

/// Attributes shared by the app (which starts and updates the activity) and the
/// widget extension (which renders it). The file is compiled into both targets.
struct MatchupActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var week: Int
        var teamName: String
        var record: String
        var projected: Double
        var points: Double
        var opponentName: String?
        var opponentProjected: Double?
        var opponentPoints: Double?
        var updated: Date
    }

    var leagueName: String
}
