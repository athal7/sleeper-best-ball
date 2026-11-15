import WidgetKit
import SwiftUI
import BestBallKit

private extension Double {
    var scoreText: String { String(format: "%.1f", self) }
}

// MARK: - Timeline

struct SnapshotEntry: TimelineEntry {
    let date: Date
    let snapshot: WidgetSnapshot?
}

struct SnapshotProvider: TimelineProvider {
    func placeholder(in context: Context) -> SnapshotEntry {
        SnapshotEntry(date: Date(), snapshot: .preview)
    }

    func getSnapshot(in context: Context, completion: @escaping (SnapshotEntry) -> Void) {
        completion(SnapshotEntry(date: Date(), snapshot: SharedStore.loadSnapshot() ?? .preview))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<SnapshotEntry>) -> Void) {
        Task {
            let entry = await Self.currentEntry()
            let refresh = Calendar.current.date(byAdding: .minute, value: 30, to: Date())
                ?? Date().addingTimeInterval(30 * 60)
            completion(Timeline(entries: [entry], policy: .after(refresh)))
        }
    }

    /// Refreshes from Sleeper when the league is configured, falling back to
    /// the last snapshot the app saved.
    private static func currentEntry() async -> SnapshotEntry {
        let now = Date()
        guard let config = SharedStore.loadConfig() else {
            return SnapshotEntry(date: now, snapshot: SharedStore.loadSnapshot())
        }
        do {
            let week = try await BestBallService().loadWeek(
                leagueID: config.leagueID,
                week: config.week,
                userID: config.userID
            )
            if let snapshot = week.widgetSnapshot() {
                SharedStore.saveSnapshot(snapshot)
                return SnapshotEntry(date: now, snapshot: snapshot)
            }
        } catch {
            // Network or Sleeper hiccup: show the cached snapshot instead.
        }
        return SnapshotEntry(date: now, snapshot: SharedStore.loadSnapshot())
    }
}

private extension WidgetSnapshot {
    static let preview = WidgetSnapshot(
        leagueName: "Sunday Best Ball",
        week: 9,
        teamName: "Fourth and Long",
        record: "6-2",
        rank: 2,
        projected: 128.4,
        points: 74.2,
        opponentName: "Bench Warmers",
        opponentProjected: 121.7,
        opponentPoints: 68.9,
        updated: Date()
    )
}

// MARK: - Widget

struct BestBallWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "BestBallWidget", provider: SnapshotProvider()) { entry in
            BestBallWidgetView(entry: entry)
        }
        .configurationDisplayName("Weekly Matchup")
        .description("Your best-ball projection for this week.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

@main
struct BestBallWidgetBundle: WidgetBundle {
    var body: some Widget {
        BestBallWidget()
        MatchupLiveActivityWidget()
    }
}

// MARK: - Views

struct BestBallWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: SnapshotEntry

    var body: some View {
        Group {
            if let snapshot = entry.snapshot {
                switch family {
                case .systemMedium:
                    MediumMatchupView(snapshot: snapshot)
                default:
                    SmallMatchupView(snapshot: snapshot)
                }
            } else {
                EmptyWidgetView()
            }
        }
        .containerBackground(for: .widget) {
            LinearGradient(
                colors: [Color(red: 0.07, green: 0.10, blue: 0.18),
                         Color(red: 0.12, green: 0.17, blue: 0.28)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        }
    }
}

struct SmallMatchupView: View {
    let snapshot: WidgetSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(snapshot.leagueName.uppercased())
                .font(.system(size: 9, weight: .bold))
                .tracking(0.8)
                .foregroundStyle(.white.opacity(0.55))
                .lineLimit(1)

            Text(snapshot.teamName)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .lineLimit(1)

            Spacer(minLength: 2)

            Text(snapshot.projected.scoreText)
                .font(.system(size: 30, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.white)

            Text("Week \(snapshot.week) projection")
                .font(.system(size: 9))
                .foregroundStyle(.white.opacity(0.55))

            if let name = snapshot.opponentName, let projected = snapshot.opponentProjected {
                Text("vs \(name) · \(projected.scoreText)")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.white.opacity(0.8))
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}

struct MediumMatchupView: View {
    let snapshot: WidgetSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(snapshot.leagueName.uppercased())
                    .font(.system(size: 10, weight: .bold))
                    .tracking(0.8)
                    .foregroundStyle(.white.opacity(0.55))
                    .lineLimit(1)
                Spacer()
                Text("WEEK \(snapshot.week)")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.white.opacity(0.55))
            }

            HStack(alignment: .top, spacing: 12) {
                column(name: snapshot.teamName,
                       record: snapshot.record,
                       projected: snapshot.projected,
                       points: snapshot.points,
                       trailing: false)

                Text("vs")
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.4))
                    .padding(.top, 22)

                column(name: snapshot.opponentName ?? "Bye",
                       record: nil,
                       projected: snapshot.opponentProjected,
                       points: snapshot.opponentPoints,
                       trailing: true)
            }

            Spacer(minLength: 0)

            Text("Updated \(snapshot.updated.formatted(.dateTime.hour().minute()))")
                .font(.system(size: 9))
                .foregroundStyle(.white.opacity(0.4))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private func column(name: String, record: String?, projected: Double?,
                        points: Double?, trailing: Bool) -> some View {
        VStack(alignment: trailing ? .trailing : .leading, spacing: 2) {
            Text(name)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .lineLimit(1)
            if let record {
                Text(record)
                    .font(.system(size: 9))
                    .foregroundStyle(.white.opacity(0.5))
            }
            Text(projected?.scoreText ?? "–")
                .font(.system(size: 26, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.white)
            if let points {
                Text("\(points.scoreText) pts")
                    .font(.system(size: 9))
                    .foregroundStyle(.white.opacity(0.5))
            }
        }
        .frame(maxWidth: .infinity, alignment: trailing ? .trailing : .leading)
    }
}

struct EmptyWidgetView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: "football")
                .font(.title3)
                .foregroundStyle(.white.opacity(0.7))
            Text("Open Best Ball and pick a league to see your matchup here.")
                .font(.caption2)
                .foregroundStyle(.white.opacity(0.7))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }
}
