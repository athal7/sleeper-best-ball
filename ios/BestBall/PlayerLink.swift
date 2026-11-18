import SwiftUI
import UIKit
import BestBallKit

// MARK: - Player handoff

/// A tappable player anywhere in the app.
///
/// Tapping opens the Sleeper app. It has no per-player deep link — its universal
/// links cover only its chat pages (`/topics/`, `/channels/`, `/message/`) and the
/// `sleeper://` scheme has no documented player route, so it opens on its home
/// screen rather than the player. When the app is not installed the tap falls
/// through to the player's web profile, which does land on the player.
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

    static var appURL: URL? { URL(string: "sleeper://") }
}

// MARK: - The name itself

/// A player's name, tappable. Drop-in replacement for the plain `Text` the rows
/// used, so every view that lists players hands off to Sleeper the same way.
struct PlayerNameButton: View {
    let player: PlayerLink
    var font: Font = .subheadline
    var weight: Font.Weight = .regular

    var body: some View {
        Button(action: openInSleeperApp) {
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
        .accessibilityHint("Opens this player in Sleeper")
    }

    /// One tap, no chooser: the app if it takes the URL, else the web profile.
    private func openInSleeperApp() {
        guard let appURL = PlayerLink.appURL else { return }
        UIApplication.shared.open(appURL, options: [:]) { opened in
            guard !opened, let webURL = player.webURL else { return }
            UIApplication.shared.open(webURL)
        }
    }
}
