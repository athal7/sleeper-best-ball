import SwiftUI
import BestBallKit

struct MatchupsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationStack {
            List {
                weekHeader

                if let error = model.errorMessage {
                    errorSection(error)
                }

                if model.visibleLeagues.isEmpty {
                    if model.isLoading {
                        loadingSection
                    } else if model.errorMessage == nil {
                        Section {
                            ContentUnavailableView(
                                "No matchups for week \(model.week)",
                                systemImage: "calendar.badge.exclamationmark",
                                description: Text("Sleeper hasn't published pairings for this week yet.")
                            )
                        }
                    }
                } else {
                    if hasMultipleMatchups {
                        filterSection
                    }

                    ForEach(model.visibleLeagues, id: \.leagueID) { leagueWeek in
                        leagueSection(leagueWeek)
                    }
                }

                liveActivitySection
            }
            .navigationTitle("My Scores")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        model.signOut()
                    } label: {
                        Label("Change account", systemImage: "person.crop.circle")
                    }
                }
            }
            .refreshable { await model.refresh() }
            .overlay {
                if model.isLoading, !model.leagueWeeks.isEmpty {
                    ProgressView()
                        .padding(12)
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                }
            }
        }
    }

    // MARK: Sections

    /// Arrows only — the week title is a label, not a picker.
    private var weekHeader: some View {
        Section {
            HStack(spacing: 12) {
                stepButton(systemImage: "chevron.left") {
                    await model.showPreviousWeek()
                }
                .disabled(model.week <= AppModel.weeks.lowerBound)

                Spacer(minLength: 0)

                VStack(spacing: 2) {
                    Text("Week \(model.week)")
                        .font(.headline)
                    Text(weekSubtitle)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Spacer(minLength: 0)

                stepButton(systemImage: "chevron.right") {
                    await model.showNextWeek()
                }
                .disabled(model.week >= AppModel.weeks.upperBound)
            }
            .padding(.vertical, 4)
        }
    }

    private var weekSubtitle: String {
        guard let state = model.state else { return "" }
        return model.week == state.defaultWeek ? "Current week" : "\(model.visibleLeagues.count) leagues"
    }

    private func stepButton(systemImage: String, action: @escaping () async -> Void) -> some View {
        Button {
            Task { await action() }
        } label: {
            Image(systemName: systemImage)
                .font(.subheadline.weight(.semibold))
                .frame(width: 28, height: 24)
        }
        .buttonStyle(.bordered)
        .buttonBorderShape(.roundedRectangle(radius: 8))
        .controlSize(.small)
    }

    private var hasMultipleMatchups: Bool {
        model.leagueWeeks.contains { $0.userRosterID != nil && $0.matchups.count > 1 }
    }

    private var filterSection: some View {
        Section {
            Picker("Matchups", selection: $model.showOnlyMyMatchups) {
                Text("Mine").tag(true)
                Text("All").tag(false)
            }
            .pickerStyle(.segmented)
            .listRowInsets(EdgeInsets(top: 4, leading: 4, bottom: 4, trailing: 4))
            .listRowBackground(Color.clear)
        }
    }

    private func leagueSection(_ leagueWeek: LeagueWeek) -> some View {
        Section {
            ForEach(model.matchups(in: leagueWeek)) { matchup in
                NavigationLink {
                    MatchupDetailView(matchup: matchup, week: leagueWeek)
                } label: {
                    MatchupCard(matchup: matchup, userRosterID: leagueWeek.userRosterID)
                }
            }
        } header: {
            Text(leagueWeek.leagueName)
        }
    }

    private var liveActivitySection: some View {
        Section {
            Toggle(isOn: liveActivityBinding) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Live scores on Lock Screen")
                    Text(liveActivityDetail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .tint(.green)
        } footer: {
            Text("Keeps this week's scores on your Lock Screen and in the Dynamic Island, one card per league. Updates whenever you pull to refresh here — no server involved.")
        }
    }

    private var liveActivityDetail: String {
        guard model.isTrackingLiveActivity else { return "Off" }
        let count = model.trackedLeagueCount
        return count == 1 ? "Tracking 1 league" : "Tracking \(count) leagues"
    }

    private var liveActivityBinding: Binding<Bool> {
        Binding(
            get: { model.isTrackingLiveActivity },
            set: { _ in Task { await model.toggleLiveActivity() } }
        )
    }

    private var loadingSection: some View {
        Section {
            HStack(spacing: 12) {
                ProgressView()
                Text("Loading scores…")
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func errorSection(_ error: String) -> some View {
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
}
