import SwiftUI
import BestBallKit

// MARK: - Trades

/// Win-win trade suggestions, one section per league, plus a link into the
/// analyzer for any two teams. The iOS twin of the Streamlit Trade Suggestions
/// view.
struct TradesView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                if model.trades.isEmpty, model.isScanningTrades || !model.hasScannedTrades {
                    // Analyzing is not the same as "no trades": show work in
                    // progress until a scan has actually finished.
                    Section {
                        HStack(spacing: 12) {
                            ProgressView()
                            Text("Scoring trade offers…")
                                .foregroundStyle(.secondary)
                        }
                        Text("Comparing every roster against the other teams in each league. This takes a few seconds per league.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } else if model.trades.isEmpty {
                    Section {
                        ContentUnavailableView(
                            "No trades worth making",
                            systemImage: "checkmark.seal",
                            description: Text("No swap improves both teams by more than 1 point per week, so standing pat is the right move.")
                        )
                    }
                } else {
                    // Very likely the same offer set the web's "All win-win
                    // trades in this league" blocks list, under "### Partner".
                    ForEach(leagues) { league in
                        Section {
                            ForEach(league.partners) { partner in
                                PartnerHeaderRow(name: partner.name)
                                ForEach(partner.offers) { offer in
                                    TradeOfferRow(offer: offer)
                                }
                            }
                        } header: {
                            Text(league.name)
                        } footer: {
                            Text("League ID: \(league.id)")
                        }
                    }

                    Section {
                        if model.isScanningTrades {
                            HStack(spacing: 12) {
                                ProgressView()
                                Text("Rescoring trade offers…")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Button {
                            Task { await model.refreshTrades() }
                        } label: {
                            Label(model.isScanningTrades ? "Rescanning…" : "Rescan",
                                  systemImage: "arrow.clockwise")
                        }
                        .disabled(model.isScanningTrades)
                    } footer: {
                        Text("Projected points gained per week over the rest of the season, playoff weeks counted 1.5×. It's an estimate: it ignores injuries, bidding wars, and who else wants the same player.")
                    }
                }

                analyzerSection
            }
            .navigationTitle("Trades")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .task {
                if !model.hasScannedTrades, !model.isScanningTrades {
                    await model.refreshTrades()
                }
            }
        }
    }

    /// Offers grouped per league, then per partner, keeping the scan's ranking.
    private var leagues: [LeagueTrades] {
        var order: [String] = []
        var names: [String: String] = [:]
        var byLeague: [String: [TradeOffer]] = [:]
        for offer in model.trades {
            if names[offer.leagueID] == nil {
                order.append(offer.leagueID)
                names[offer.leagueID] = offer.leagueName
            }
            byLeague[offer.leagueID, default: []].append(offer)
        }
        return order.compactMap { leagueID in
            guard let offers = byLeague[leagueID] else { return nil }
            var partnerOrder: [String] = []
            var partnerNames: [String: String] = [:]
            var byPartner: [String: [TradeOffer]] = [:]
            for offer in offers {
                if partnerNames[offer.partnerID] == nil {
                    partnerOrder.append(offer.partnerID)
                    partnerNames[offer.partnerID] = offer.partnerName
                }
                byPartner[offer.partnerID, default: []].append(offer)
            }
            let partners = partnerOrder.compactMap { partnerID -> PartnerTrades? in
                guard let offers = byPartner[partnerID] else { return nil }
                return PartnerTrades(
                    id: partnerID,
                    name: partnerNames[partnerID] ?? "Trade partner",
                    offers: offers
                )
            }
            return LeagueTrades(id: leagueID, name: names[leagueID] ?? "", partners: partners)
        }
    }

    private var analyzerSection: some View {
        Section {
            if model.tradeBoards.isEmpty {
                Text("Analyze a trade once offers load.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(model.tradeBoards) { board in
                    NavigationLink {
                        TradeAnalyzerView(board: board)
                    } label: {
                        Label(board.name, systemImage: "slider.horizontal.3")
                    }
                }
            }
        } header: {
            Text("Trade analyzer")
        } footer: {
            Text("Pick two teams and an optional position need each, then see every offer that helps both of them.")
        }
    }
}

private struct LeagueTrades: Identifiable {
    let id: String
    let name: String
    let partners: [PartnerTrades]
}

private struct PartnerTrades: Identifiable {
    let id: String
    let name: String
    let offers: [TradeOffer]
}

/// The partner each block of offers is for, like the `#### name` heading the
/// Streamlit table puts above a group.
private struct PartnerHeaderRow: View {
    let name: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: "person.crop.circle")
                .font(.caption2)
                .foregroundStyle(.secondary)

            Text(name)
                .font(.subheadline.weight(.semibold))
                .lineLimit(1)
        }
        .listRowBackground(Color(uiColor: .secondarySystemGroupedBackground).opacity(0.5))
        .padding(.top, 4)
    }
}

/// One offer: what you send on the left, what you get back on the right, each
/// side with its own projected weekly gain.
private struct TradeOfferRow: View {
    let offer: TradeOffer

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            side(title: "You get", gain: offer.myUplift,
                 players: offer.receive, systemImage: "plus.circle.fill", tint: .green)

            Divider()

            side(title: "They get", gain: offer.partnerUplift,
                 players: offer.give, systemImage: "minus.circle.fill", tint: .red)
        }
        .padding(.vertical, 2)
    }

    private func side(title: String, gain: Double, players: [TradeAsset],
                      systemImage: String, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                Text(title)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 2)
                Text("+\(String(format: "%.1f", gain))")
                    .font(.caption.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.green)
            }

            ForEach(players) { player in
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 3) {
                        Image(systemName: systemImage)
                            .font(.system(size: 8))
                            .foregroundStyle(tint)
                        // Names open the Sleeper web profile, like the links in
                        // the web trade table.
                        playerLink(for: player)
                    }
                    Text(player.detailText)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .padding(.leading, 11)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func playerLink(for player: TradeAsset) -> some View {
        if let url = player.profileURL {
            Link(destination: url) {
                Text(player.name)
                    .font(.subheadline)
                    .lineLimit(1)
            }
            .buttonStyle(.plain)
            .tint(.primary)
        } else {
            Text(player.name)
                .font(.subheadline)
                .lineLimit(1)
        }
    }
}

// MARK: - Analyzer

/// Two teams, an optional position need each, and every offer above zero — the
/// Streamlit app's "Trade analyzer" panel.
struct TradeAnalyzerView: View {
    let board: TradeBoard

    @State private var teamA: String
    @State private var teamB: String
    @State private var needA = TradeAnalyzerView.anyPosition
    @State private var needB = TradeAnalyzerView.anyPosition
    @State private var offers: [TradeOffer] = []
    @State private var totalOffers = 0
    @State private var isComputing = false

    static let anyPosition = "Any position"
    /// The web table shows five offers per partner; keep the same ceiling.
    private static let visibleOffers = 5

    init(board: TradeBoard) {
        self.board = board
        let mine = board.userTeamID ?? board.teams.first?.id ?? ""
        let partner = board.teams.first { $0.id != mine }?.id ?? ""
        _teamA = State(initialValue: mine)
        _teamB = State(initialValue: partner)
    }

    var body: some View {
        List {
            Section {
                Picker("Team 1", selection: $teamA) {
                    ForEach(board.teams) { team in
                        Text(label(for: team)).tag(team.id)
                    }
                }
                Picker("Team 1 need", selection: $needA) {
                    Text(Self.anyPosition).tag(Self.anyPosition)
                    ForEach(board.positions, id: \.self) { position in
                        Text(position).tag(position)
                    }
                }
                Picker("Team 2", selection: $teamB) {
                    ForEach(board.teams) { team in
                        Text(label(for: team)).tag(team.id)
                    }
                }
                Picker("Team 2 need", selection: $needB) {
                    Text(Self.anyPosition).tag(Self.anyPosition)
                    ForEach(board.positions, id: \.self) { position in
                        Text(position).tag(position)
                    }
                }
            } header: {
                Text("Teams")
            }

            if teamA == teamB {
                Section {
                    Text("Pick two different teams to analyze a trade.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else if isComputing {
                Section {
                    HStack(spacing: 12) {
                        ProgressView()
                        Text("Comparing lineups…")
                            .foregroundStyle(.secondary)
                    }
                }
            } else if offers.isEmpty {
                Section {
                    Text("No trades improve both teams. Try a different pair or opening up the position needs.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                Section {
                    ForEach(offers) { offer in
                        TradeOfferRow(offer: offer)
                    }
                } header: {
                    Text("\(totalOffers) trades help both teams")
                } footer: {
                    Text("Showing the \(offers.count) best. Projected gain per week over the rest of the season, playoff weeks counted 1.5×.")
                }
            }
        }
        .navigationTitle(board.name)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: request) { await recompute() }
    }

    private func label(for team: TradeTeam) -> String {
        team.id == board.userTeamID ? "Your team" : team.name
    }

    /// Re-runs the search whenever a picker changes. The work happens off the
    /// main actor because a full 12-team league is thousands of lineups.
    private var request: String {
        "\(teamA)|\(teamB)|\(needA)|\(needB)"
    }

    private func recompute() async {
        guard teamA != teamB else {
            offers = []
            totalOffers = 0
            return
        }
        isComputing = true

        let board = board
        let myTeam = teamA
        let partner = teamB
        let myNeed = needA == Self.anyPosition ? nil : needA
        let partnerNeed = needB == Self.anyPosition ? nil : needB
        let limit = Self.visibleOffers

        let result = await Task.detached(priority: .userInitiated) {
            board.analyze(
                myTeamID: myTeam,
                partnerTeamID: partner,
                myNeed: myNeed,
                partnerNeed: partnerNeed,
                minUplift: 0
            )
        }.value

        guard !Task.isCancelled else { return }
        totalOffers = result.count
        offers = Array(result.prefix(limit))
        isComputing = false
    }
}
