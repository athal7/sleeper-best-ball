import SwiftUI
import UIKit
import BestBallKit

// MARK: - Player handoff

/// A tappable player anywhere in the app.
///
/// Sleeper gives us two places to send someone: its web profile for that player,
/// and the app itself. The app has no per-player deep link — its universal links
/// cover only its chat pages (`/topics/`, `/channels/`, `/message/`) and the
/// `sleeper://` scheme has no documented player route, so it opens on its home
/// screen. Tapping therefore offers the app when it is installed, plus the web
/// profile, and falls straight through to the profile when it is not.
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

    /// The page the Streamlit app links to.
    var webURL: URL? { SleeperProfile.url(name: name, id: id) }

    /// Whether Sleeper's app is on this phone. Needs `sleeper` in
    /// `LSApplicationQueriesSchemes` (see Info.plist) or this is always false.
    static var appIsInstalled: Bool {
        guard let url = appURL else { return false }
        return UIApplication.shared.canOpenURL(url)
    }

    static var appURL: URL? { URL(string: "sleeper://") }
}

// MARK: - The name itself

/// A player's name, tappable. Drop-in replacement for the plain `Text` the rows
/// used, so every view that lists players hands off to Sleeper the same way.
struct PlayerNameButton: View {
    let player: PlayerLink
    var font: Font = .subheadline
    var weight: Font.Weight = .regular

    @State private var showingOptions = false

    var body: some View {
        Button(action: tap) {
            Text(player.name)
                .font(font.weight(weight))
                .lineLimit(1)
                .foregroundStyle(.primary)
        }
        .buttonStyle(.plain)
        .accessibilityHint("Opens this player in Sleeper")
        .confirmationDialog(player.name, isPresented: $showingOptions, titleVisibility: .visible) {
            Button("Open in Sleeper app") { open(PlayerLink.appURL) }
            if let url = player.webURL {
                Button("Player page on sleeper.com") { open(url) }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Sleeper has no per-player app link yet, so its app opens on the home screen.")
        }
    }

    private func tap() {
        if PlayerLink.appIsInstalled {
            showingOptions = true
        } else if let url = player.webURL {
            open(url)
        }
    }

    private func open(_ url: URL?) {
        guard let url else { return }
        UIApplication.shared.open(url)
    }
}
