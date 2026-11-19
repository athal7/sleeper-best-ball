import SwiftUI
import UIKit
import BestBallKit

// MARK: - Player handoff

/// A tappable player anywhere in the app.
///
/// Tapping opens the player's Sleeper page. Sleeper's app has no per-player deep
/// link to open — the universal links it registers (see the AASA for
/// sleeper.com) cover only its chat pages, and `sleeper://` with no path hands
/// you back to whatever screen the app last showed, which is why the old tap
/// landed on a league matchup. The profile URL is the one address that actually
/// resolves to the player, so it is opened directly instead of trying the app
/// first.
struct PlayerLink: Identifiable, Hashable {
    let id: String
    let name: String

    init(id: String, name: String) {
        self.id = id
        self.name = name
    }

    init(_ asset: TradeAsset) {
        self.init(id: asset.id, name: asset.name)
    }

    init(_ player: RosterPlayer) {
        self.init(id: player.id, name: player.name)
    }

    /// The page the Streamlit app links to, and the one this tap opens.
    var webURL: URL? { SleeperProfile.url(name: name, id: id) }
}

// MARK: - The name itself

/// A player's name, tappable. Drop-in replacement for the plain `Text` the rows
/// used, so every view that lists players hands off to Sleeper the same way.
struct PlayerNameButton: View {
    let player: PlayerLink
    var font: Font = .subheadline
    var weight: Font.Weight = .regular

    var body: some View {
        Button(action: openPlayer) {
            Text(player.name)
                .font(font.weight(weight))
                .lineLimit(1)
                .foregroundStyle(.primary)
                // Without this the tap target is the glyphs alone, which is a
                // sliver of a row and reads as a dead label.
                .padding(.vertical, 4)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint("Opens this player's Sleeper page")
    }

    private func openPlayer() {
        guard let url = player.webURL else { return }
        UIApplication.shared.open(url)
    }
}
