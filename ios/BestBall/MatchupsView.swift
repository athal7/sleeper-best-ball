import SwiftUI
import BestBallKit

struct MatchupsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var showingWaivers = false

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

                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingWaivers = true
                    } label: {
                        Image(systemName: "arrow.left.arrow.right")
                            .overlay(alignment: .topTrailing) {
                                if model.unseenWaiverCount > 0 {
                                    Text("\(model.unseenWaiverCount)")
                                        .font(.system(size: 9, weight: .bold))
                                        .foregroundStyle(.white)
                                        .padding(.horizontal, 4)
                                        .frame(minWidth: 14, minHeight: 14)
                                        .background(Color.red, in: Capsule())
                                        .offset(x: 8, y: -6)
                                }
                            }
                    }
                    .accessibilityLabel("Waiver suggestions")
                }
            }
            .refreshable { await model.refresh() }
            .sheet(isPresented: $showingWaivers) {
                WaiversView()
                    .environmentObject(model)
            }
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

// MARK: - Waivers

/// Add/drop suggestions, one section per league. Lives here rather than in its
/// own file so the hand-written project file doesn't need another entry.
struct WaiversView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss

    private var groups: [(leagueID: String, leagueName: String, picks: [WaiverPick])] {
        var order: [String] = []
        var byLeague: [String: [WaiverPick]] = [:]
        for pick in model.waivers {
            if byLeague[pick.leagueID] == nil { order.append(pick.leagueID) }
            byLeague[pick.leagueID, default: []].append(pick)
        }
        return order.compactMap { leagueID in
            guard let picks = byLeague[leagueID], let first = picks.first else { return nil }
            return (leagueID, first.leagueName, picks)
        }
    }

    var body: some View {
        NavigationStack {
            List {
                if model.waivers.isEmpty {
                    Section {
                        if model.isScanningWaivers {
                            HStack(spacing: 12) {
                                ProgressView()
                                Text("Scoring free agents…")
                                    .foregroundStyle(.secondary)
                            }
                        } else if model.waiverEligibleLeagues == 0, model.bestBallLeagues > 0 {
                            ContentUnavailableView(
                                "Best-ball leagues have no wire",
                                systemImage: "lock",
                                description: Text("All \(model.bestBallLeagues) of your leagues are best ball: Sleeper locks rosters after the draft, so there are no adds, drops, or trades to recommend. This screen fills in for any league that allows moves.")
                            )
                        } else {
                            ContentUnavailableView(
                                "No adds worth making",
                                systemImage: "checkmark.seal",
                                description: Text("Nothing on the wire improves your lineup by a point or more. That's usually good news.")
                            )
                        }
                    }
                } else {
                    ForEach(groups, id: \.leagueID) { group in
                        Section(group.leagueName) {
                            ForEach(group.picks) { pick in
                                WaiverRow(pick: pick)
                            }
                        }
                    }

                    Section {
                        Button {
                            Task { await model.refreshWaivers(notify: false) }
                        } label: {
                            Label("Rescan", systemImage: "arrow.clockwise")
                        }
                        .disabled(model.isScanningWaivers)
                    } footer: {
                        Text("Projected points gained over the rest of the season, playoff weeks counted 1.5×. It's an estimate: it ignores injuries, bidding wars, and who else wants the same player.")
                    }
                }
            }
            .navigationTitle("Waivers")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .task { model.markWaiversSeen() }
        }
    }
}

private struct WaiverRow: View {
    let pick: WaiverPick

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("Add \(pick.addName)")
                    .font(.subheadline.weight(.semibold))
                Spacer(minLength: 8)
                Text("+\(String(format: "%.1f", pick.uplift))")
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.green)
            }
            Text("\(pick.addPosition) · \(pick.addTeam)  ·  drop \(pick.dropName) (\(pick.dropPosition))")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }
}
