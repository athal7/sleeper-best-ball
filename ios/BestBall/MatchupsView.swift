import SwiftUI
import BestBallKit

struct MatchupsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var showingWaivers = false
    @State private var showingTrades = false
    @State private var showingTips = false

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

                Section {
                    Button {
                        showingTips = true
                    } label: {
                        Label("Send a tip", systemImage: "heart")
                    }
                } footer: {
                    Text("The app is free and ad-free. Tips go straight to the developer through the App Store.")
                }
            }
            .navigationTitle("My Scores")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        model.disconnect()
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

                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingTrades = true
                    } label: {
                        Image(systemName: "arrow.2.squarepath")
                    }
                    .accessibilityLabel("Trade suggestions")
                }
            }
            .refreshable { await model.refresh() }
            .sheet(isPresented: $showingWaivers) {
                WaiversView()
                    .environmentObject(model)
            }
            .sheet(isPresented: $showingTrades) {
                TradesView()
                    .environmentObject(model)
            }
            .sheet(isPresented: $showingTips) {
                TipJarView()
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
            .disabled(!model.liveActivitiesAuthorized)
        } footer: {
            Text(liveActivityFooter)
        }
    }

    private var liveActivityDetail: String {
        guard model.liveActivitiesAuthorized else { return "Off in iOS Settings" }
        guard model.isTrackingLiveActivity else { return "Starts when a game is on" }
        let count = model.trackedLeagueCount
        return count == 1 ? "Tracking 1 league" : "Tracking \(count) leagues"
    }

    private var liveActivityFooter: String {
        guard model.liveActivitiesAuthorized else {
            return "Live Activities are turned off for Best Ball in Settings, so no card can appear until you allow them there."
        }
        return "While you have a player in a game, this week's scores sit on your Lock Screen and in the Dynamic Island, one card per league — it turns itself on at kickoff and goes away once the week's games are done. Scores refresh when the app does, including the background refresh iOS schedules; no server is involved."
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

    /// Grouped the way the Streamlit waiver guide reads: per league, then per
    /// player you'd drop, with the adds that player would make room for under it.
    private var leagues: [LeagueWaivers] {
        var order: [String] = []
        var names: [String: String] = [:]
        var byDrop: [String: [String: [WaiverPick]]] = [:]
        for pick in model.waivers {
            if names[pick.leagueID] == nil {
                order.append(pick.leagueID)
                names[pick.leagueID] = pick.leagueName
            }
            byDrop[pick.leagueID, default: [:]][pick.dropID, default: []].append(pick)
        }
        return order.compactMap { leagueID in
            guard let drops = byDrop[leagueID] else { return nil }
            let groups = drops.compactMap { dropID, picks -> DropGroup? in
                guard let first = picks.first else { return nil }
                return DropGroup(id: dropID, drop: first, adds: picks)
            }
            .sorted { lhs, rhs in
                let left = lhs.adds.map(\.uplift).max() ?? 0
                let right = rhs.adds.map(\.uplift).max() ?? 0
                return left > right
            }
            return LeagueWaivers(id: leagueID, name: names[leagueID] ?? "", drops: groups)
        }
    }

    var body: some View {
        NavigationStack {
            List {
                if model.waivers.isEmpty {
                    Section {
                        // A scan that hasn't finished is not an empty result.
                        if model.isScanningWaivers || !model.hasScannedWaivers {
                            HStack(spacing: 12) {
                                ProgressView()
                                Text("Scoring free agents…")
                                    .foregroundStyle(.secondary)
                            }
                            Text("Checking every roster against the waiver wire. This takes a few seconds per league.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            ContentUnavailableView(
                                "No adds worth making",
                                systemImage: "checkmark.seal",
                                description: Text("No free agent improves your projected lineup by more than 1 point per week, so standing pat is the right move.")
                            )
                        }
                    }
                } else {
                    ForEach(leagues) { league in
                        Section(league.name) {
                            ForEach(league.drops) { group in
                                DropHeaderRow(pick: group.drop)
                                ForEach(group.adds) { pick in
                                    WaiverRow(pick: pick)
                                }
                            }
                        }
                    }

                    Section {
                        if model.isScanningWaivers {
                            HStack(spacing: 12) {
                                ProgressView()
                                Text("Rescoring free agents…")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Button {
                            Task { await model.refreshWaivers(notify: false) }
                        } label: {
                            Label(model.isScanningWaivers ? "Rescanning…" : "Rescan",
                                  systemImage: "arrow.clockwise")
                        }
                        .disabled(model.isScanningWaivers)
                    } footer: {
                        Text("Projected points gained per week over the rest of the season, playoff weeks counted 1.5×. It's an estimate: it ignores injuries, bidding wars, and who else wants the same player.")
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

private struct LeagueWaivers: Identifiable {
    let id: String
    let name: String
    let drops: [DropGroup]
}

private struct DropGroup: Identifiable {
    let id: String
    let drop: WaiverPick
    let adds: [WaiverPick]
}

/// Heading for the player a group of adds would replace, matching the `− Name`
/// row the Streamlit waiver guide puts above each block.
private struct DropHeaderRow: View {
    let pick: WaiverPick

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: "minus.circle.fill")
                .font(.caption2)
                .foregroundStyle(.red)

            Text("Drop")
                .font(.subheadline.weight(.semibold))
            PlayerNameButton(player: PlayerLink(id: pick.dropID, name: pick.dropName),
                             weight: .semibold)

            Spacer(minLength: 6)

            Text("\(pick.dropPosition) · \(pick.dropTeam)")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .listRowBackground(Color(uiColor: .secondarySystemGroupedBackground).opacity(0.5))
        .padding(.top, 4)
    }
}

private struct WaiverRow: View {
    let pick: WaiverPick

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: "plus.circle.fill")
                    .font(.caption2)
                    .foregroundStyle(.green)

                PlayerNameButton(player: PlayerLink(id: pick.addID, name: pick.addName),
                                 weight: .medium)

                Spacer(minLength: 6)

                if pick.isUpgrade {
                    Text("+\(String(format: "%.1f", pick.uplift))")
                        .font(.subheadline.weight(.semibold).monospacedDigit())
                        .foregroundStyle(.green)
                } else {
                    Text("best available")
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(.secondary)
                }
            }
            Text("\(pick.addPosition) · \(pick.addTeam)")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.leading, 16)
        }
        .padding(.vertical, 1)
    }
}
