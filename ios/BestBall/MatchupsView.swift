import SwiftUI
import BestBallKit

struct MatchupsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationStack {
            List {
                weekSection

                if let error = model.errorMessage {
                    Section {
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Couldn't load this week", systemImage: "exclamationmark.triangle")
                                .font(.subheadline.weight(.semibold))
                            Text(error)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Button("Try again") {
                                Task { await model.refresh() }
                            }
                            .font(.subheadline.weight(.semibold))
                        }
                        .padding(.vertical, 4)
                    }
                }

                if let week = model.week {
                    if week.matchups.isEmpty {
                        Section {
                            ContentUnavailableView(
                                "No matchups for week \(week.week)",
                                systemImage: "calendar.badge.exclamationmark",
                                description: Text("Sleeper hasn't published pairings for this week yet.")
                            )
                        }
                    } else {
                        Section {
                            ForEach(week.matchups) { matchup in
                                NavigationLink {
                                    MatchupDetailView(matchup: matchup, week: week)
                                } label: {
                                    MatchupCard(matchup: matchup, userRosterID: week.userRosterID)
                                }
                            }
                        } footer: {
                            Text("Projections assume each player keeps scoring at their projected pace for the rest of their game. Best-ball lineups are set automatically.")
                        }
                    }
                } else if model.isLoading {
                    Section {
                        HStack(spacing: 12) {
                            ProgressView()
                            Text("Loading week \(model.config?.week ?? 1)…")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle(model.config?.leagueName ?? "Matchups")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        model.signOut()
                    } label: {
                        Label("Change league", systemImage: "person.crop.circle")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    liveActivityButton
                }
                ToolbarItem(placement: .topBarTrailing) {
                    weekMenu
                }
            }
            .refreshable { await model.refresh() }
            .overlay {
                if model.isLoading, model.week != nil {
                    ProgressView()
                        .padding(12)
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                }
            }
        }
    }

    private var weekSection: some View {
        Section {
            HStack {
                Button {
                    Task { await model.showPreviousWeek() }
                } label: {
                    Image(systemName: "chevron.left")
                }
                .buttonStyle(.borderless)
                .disabled((model.week?.week ?? 1) <= AppModel.weeks.lowerBound)

                Spacer()

                VStack(spacing: 2) {
                    Text("Week \(model.week?.week ?? model.config?.week ?? 1)")
                        .font(.headline)
                    if let state = model.state, (model.week?.week ?? 0) == state.defaultWeek {
                        Text("Current week")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                Button {
                    Task { await model.showNextWeek() }
                } label: {
                    Image(systemName: "chevron.right")
                }
                .buttonStyle(.borderless)
                .disabled((model.week?.week ?? 1) >= AppModel.weeks.upperBound)
            }
            .padding(.vertical, 2)
        }
    }

    private var liveActivityButton: some View {
        Button {
            Task { await model.toggleLiveActivity() }
        } label: {
            Label(
                model.isTrackingLiveActivity ? "Stop Live Activity" : "Track matchup live",
                systemImage: model.isTrackingLiveActivity
                    ? "bolt.horizontal.circle.fill"
                    : "bolt.horizontal.circle"
            )
        }
        .disabled(model.week == nil)
    }

    private var weekMenu: some View {
        Menu {
            ForEach(AppModel.weeks, id: \.self) { week in
                Button {
                    Task { await model.load(week: week) }
                } label: {
                    if week == (model.week?.week ?? model.config?.week) {
                        Label("Week \(week)", systemImage: "checkmark")
                    } else {
                        Text("Week \(week)")
                    }
                }
            }
        } label: {
            Label("Week", systemImage: "calendar")
        }
    }
}
