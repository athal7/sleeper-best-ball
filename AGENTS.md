# Agent guidance

## Layout

- `streamlit_app.py` — the whole web app (projections, waivers, trades, draft).
- `tests/` — pytest suite for the Python app.
- `ios/BestBallKit` — Swift package with all projection, lineup, waiver, and trade logic. No SwiftUI, so it is testable from the command line.
- `ios/BestBall` — SwiftUI app target. `ios/BestBallWidget` — Home Screen widget. Always change engine behavior in `BestBallKit` first, then wire it into the app.

## Verify

Web:

```bash
pip install -r requirements.txt
pytest -v --ignore=tests/test_app.py   # what CI runs
```

iOS engine:

```bash
swift test --package-path ios/BestBallKit
```

## Xcode toolchain on this machine

Xcode is installed at `/Applications/Xcode.app`, but `xcode-select` points at the
Command Line Tools. All `swift`/`xcodebuild`/`xcrun` commands below need:

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
```

Do not change the system-wide `xcode-select` selection. Without it, `xcodebuild`
refuses to run and `swift test` fails with
`external macro implementation type 'TestingMacros.TestDeclarationMacro' could not be found`.

Build check for the app (no signing needed):

```bash
xcodebuild build -project ios/BestBall.xcodeproj -scheme BestBall \
  -destination 'generic/platform=iOS Simulator' -configuration Debug \
  CODE_SIGNING_ALLOWED=NO
```

## Ship to the phone

There is no over-the-air channel in use. The maintainer installs builds over the
cable from Xcode, so a "put it on my phone" request means build for the paired
device and install it with `devicectl`:

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
xcrun devicectl list devices                       # find the paired iPhone UDID
xcodebuild build -project ios/BestBall.xcodeproj -scheme BestBall \
  -configuration Debug -destination 'id=<device-udid>' -allowProvisioningUpdates
xcrun devicectl device install app --device <device-udid> \
  "$HOME/Library/Developer/Xcode/DerivedData/BestBall-*/Build/Products/Debug-iphoneos/BestBall.app"
```

Signing is automatic with team `MH5EJ3Q33X` and bundle id `com.sleeperbestball.app`
(overridable through the `BB_BUNDLE_ID` build setting). An install is not
verification of the UI — the screen has not been looked at unless someone ran it.

## TestFlight

`.github/workflows/testflight.yml` is manual-only (`workflow_dispatch`) and is not
wired up for day-to-day shipping: the only run attempted so far never started
because GitHub had no macOS runner capacity
(`The job was not acquired by Runner of type hosted`). Do not treat a dispatched
run as the phone getting the build, and do not promise a TestFlight build without
confirming it actually archived and uploaded.

## Conventions

- `ios/BestBall.xcodeproj` has no file-system-synchronized groups. A new Swift
  file must be added by hand to `project.pbxproj` in four places: `PBXBuildFile`,
  `PBXFileReference`, the group's `children`, and the target's `Sources` build phase.
  Reuse one unique 24-character hex id per entry and check it is not already used.
- Commit subjects are Conventional Commits (`feat(ios): …`, `fix(waivers): …`),
  imperative, lowercase, under 72 characters.
- Trade and waiver numbers are user-visible and mirror the Python app. When the two
  disagree the Python implementation in `streamlit_app.py` is the reference, and
  `tests/test_trade.py` / the waiver tests are the expectations to match.
- Trade and waiver scoring slots are a quirk worth preserving: `DraftSettings.from_draft`
  reads `slots_qb`-style keys real Sleeper leagues do not have, so the web falls back
  to `from_actual_roster` — one slot per player on *your* roster, each eligible only
  for that player's own position, bench and flex included. `LineupSlots.rosterSlots`
  rebuilds exactly that, and both scanners use it. Do not "fix" it to use
  `roster_positions`: iOS then stops matching the web. Verified against live leagues
  with a Python reference of the web path — identical offers, adds, drops and uplifts.
- Trade packages are deliberately balanced where the web's are not: when one side
  would send two players for one, `TradeBoard.analyze` attaches the throw-in that
  side would cut anyway (weakest weighted rest-of-season total) and rescores. The
  row tags it `throw-in`. Keep the counts equal — a 2-for-1 leaves the receiving
  manager over the roster limit with no say in who goes, which is the bug this
  fixed. Uplifts themselves still come from the web's slot math, so they can
  differ in size between the two sides; that is the estimate, not a defect.
- Players are tappable everywhere they appear (`PlayerNameButton` in
  `ios/BestBall/PlayerLink.swift`). Sleeper publishes no per-player app link: its
  universal links cover only `/topics/`, `/channels/`, `/topic/`, `/message/`, and
  the `sleeper://` scheme has no documented player route, so the app opens on its
  home screen. The button offers the app when `canOpenURL` says it is installed
  (needs `sleeper` in `LSApplicationQueriesSchemes`) and the web profile otherwise.
- A screen that kicks off its own scan must key its `.task` on the data it needs
  (`TradesView` uses `model.leagues.count`). Opening the sheet before the leagues
  have loaded otherwise bails out of the scan and leaves the spinner running forever.
- Live Activities are gated on `RosterPlayer.isLive`: a league only gets an activity
  while at least one of the user's players is in a game that is in progress.
- The tip jar (`ios/BestBall/TipJarView.swift`) uses consumable products named
  `<bundle id>.tip.small|medium|large`. They must exist in App Store Connect for a
  paid team before any purchase works; a sideloaded build shows "unavailable", which
  is expected rather than a bug.
