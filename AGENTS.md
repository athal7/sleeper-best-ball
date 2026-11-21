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

Signing is automatic with team `FDW9E6KH3V` (Optipotamus LLC) and bundle id
`com.sleeperbestball.app` (overridable through the `BB_BUNDLE_ID` build setting).
`MH5EJ3Q33X` is a personal team: it provisions for a device but cannot mint an
App Store profile, so an export or upload under it fails. The App Store record
uses `BB_BUNDLE_ID=com.optipotamus.bestball` on the archive command line rather
than in the project, because `com.sleeperbestball.app` cannot be registered to a
paid team while the personal team holds it. An install is not verification of
the UI — the screen has not been looked at unless someone ran it.

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
- Waiver numbers are user-visible and mirror the Python app. When the two disagree
  the Python implementation in `streamlit_app.py` is the reference, and the waiver
  tests are the expectations to match.
- Waiver scoring slots keep a quirk worth preserving: `DraftSettings.from_draft`
  reads `slots_qb`-style keys real Sleeper leagues do not have, so the web falls back
  to `from_actual_roster` — one slot per player on *your* roster, each eligible only
  for that player's own position, bench and flex included. `LineupSlots.rosterSlots`
  rebuilds exactly that and `WaiverScanner` uses it. Do not "fix" waivers to use
  `roster_positions`: iOS then stops matching the web.
- Trade scoring does not follow that fallback, and both surfaces must agree on
  this. `TradeScanner` scores trades against the league's real starting lineup
  (`LineupSlots.slots(for: detail.rosterPositions)`, bench slots ignored by
  `LineupScorer`); `streamlit_app.py` does the same through
  `DraftSettings.from_roster_positions`, called from
  `_trade_suggestions_league_fragment`. Under `rosterSlots` every rostered player
  owns a slot, so a package can barely help both sides at once: Metro Master
  returned 5 offers from 1 partner, and `bergmanfam` returned none. With the real
  lineup the same two leagues return 23 offers from 7 partners and 11 offers from
  3 — bench players are worth nothing to their own team and something to the other
  one. Keep it that way; the divergence from the old web numbers is intentional.
- The two surfaces are migrating onto one engine in `core/` (Rust). It owns the
  platform-neutral arithmetic — slot expansion and eligibility, stat-line
  scoring, greedy lineup selection, and the lineup-uplift value model that
  waivers and trades are both built from. Shells pass raw inputs in (a league's
  `roster_positions`, weekly points per player) and render the results; they
  must not re-derive slot tables or uplift. The boundary is JSON over a C ABI
  (`bestball_request` / `bestball_string_free`): Swift links the static library,
  Python loads the dylib with `ctypes`.
- Layout: `core/` is the engine (`bestball_engine`), `core/bestball-py/` is the
  PyO3 wrapper that produces the `bestball_core` wheel. They are separate crates
  because a static library and a Python extension cannot share one link setup,
  and because iOS must never link libpython. Build the wheel with
  `cd core/bestball-py && ../../.venv/bin/maturin build --release` and install
  it into `.venv`; `streamlit_app.py` imports `bestball_core` and will not start
  without it.
- The web already delegates the two hottest primitives to the engine:
  `_best_lineup_score` and `compute_lineup_uplift` (which waivers and trades
  both value players with) are thin pandas adapters. What is still Python-only
  is the search around them: waiver add/drop selection, trade package building,
  and projection preparation.
- Streamlit deploys from `requirements.txt` and cannot compile Rust, so the web
  gets a prebuilt abi3 wheel. `.github/workflows/engine-wheels.yml` builds one
  per platform on an `engine-v*` tag; pin the manylinux asset in
  `requirements.txt` before deploying. Update the pin whenever engine behaviour
  changes, or the web will keep running the old numbers.
- Fidelity is pinned by shared fixtures, not by comparing two implementations.
  Every case in `core/src/lineup.rs` and `core/src/uplift.rs` has a partner of
  the same name in `tests/test_engine.py` asserting the identical number through
  the Python adapter. Add the pytest case whenever you add a Rust one; a
  behaviour change means editing both, which is the point.
- Change one surface, change the other: the trade rule also has a mirrored pair
  of tests, `leagueLineupFindsDealsTheRosterSlotFallbackMisses` in
  `BestBallKitTests` and
  `test_trades_use_the_league_lineup_not_the_users_own_roster_shape` in
  `tests/test_trade.py`, built from the same rosters.
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
  `sleeper://` has no player route, so opening the bare scheme resumes the app on
  whatever screen it last showed (a league matchup, in practice). The tap goes
  straight to the web profile at `sleeper.com/nfl/players/<slug>-<id>` instead —
  the slug is decorative, Sleeper routes on the id — with no `sleeper://` attempt
  in front of it. Keep `contentShape(Rectangle())` on the label: without it the
  hit area is the glyphs alone and the name reads as a dead label.
- A screen that kicks off its own scan must key its `.task` on the data it needs
  (`TradesView` uses `model.leagues.count`). Opening the sheet before the leagues
  have loaded otherwise bails out of the scan and leaves the spinner running forever.
- The week on screen follows Sleeper rather than staying where it was: both
  surfaces open on the later of the saved week and `defaultWeek`, and a refresh
  in the same session moves forward when the week rolls over. Only an arrow tap
  (iOS) or a week edit (web) onto a different week pins the screen, and arrowing
  back to the current week hands control to Sleeper again. This is why the
  opened week is `max(saved, current)`: a week saved before the rollover is last
  week's news, while a week parked on ahead of time is still deliberate.
- Live Activities are gated on `RosterPlayer.isLive` and start themselves:
  `syncLiveActivities` runs on every load, starts a card for each league with a
  player on the field, and ends the cards whose league dropped out — so nothing
  waits for a tap at kickoff, and a card never outlives its game. The same sync
  backs the toggle. The switch shows whether tracking is armed for the week
  (`isLiveActivityEnabled`), not whether a card is up: before kickoff there is
  nothing to show, and a switch bound to `isTrackingLiveActivity` snapped back
  off the instant it was tapped, which reads as broken. On is the default state,
  so turning it off is what does something — it writes a mute for the week
  (`liveActivityMutedWeekKey`) and ends the cards; turning it back on clears the
  mute. The mute is scoped to the week it was set in, so the next week's games
  come back on their own. A card is never started before a game is on. `BackgroundRefresh` deliberately does not check the mute: it is also what
  starts tracking and posts waiver notifications.
- The tip jar (`ios/BestBall/TipJarView.swift`) uses consumable products named
  `<bundle id>.tip.small|medium|large`. They must exist in App Store Connect for a
  paid team before any purchase works; a sideloaded build shows "unavailable", which
  is expected rather than a bug.

## Building the iOS app against the engine

- `core/scripts/build-ios.sh` builds the Rust engine into
  `ios/.engine/libbestball_engine.a`; `BestBallKit` links it and talks to it
  through `EngineBridge.swift` (JSON over the C ABI in `core/src/abi.rs`).
  There is no published framework: Xcode runs the script from a "Build engine"
  phase before Sources on both `BestBall` and `BestBallWidget`, so the archive
  always matches the SDK being built.
- That phase needs `ENABLE_USER_SCRIPT_SANDBOXING = NO`: cargo writes its own
  `core/target` tree, whose file set cannot be declared as outputs. Do not turn
  the sandbox back on without moving the Rust build outside the phase.
- `SDKROOT` must be a real SDK path when cargo runs. Xcode exports it as a name
  ("iphonesimulator"), which clang resolves relative to the working directory
  and fails on; the script converts it with `xcrun --show-sdk-path`.
- The simulator archive is lipo'd for arm64 + x86_64 (`generic/platform=iOS
  Simulator` builds both). Device and simulator archives have the same file
  name, so whichever ran last wins — that is why `swift test` needs
  `core/scripts/build-ios.sh host` first:
  `core/scripts/build-ios.sh host && cd ios/BestBallKit && swift test`.
- Command-line app builds use the shared scheme:
  `xcodebuild -project ios/BestBall.xcodeproj -scheme BestBall -destination
  'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build`. Building with
  `-target` instead skips SwiftPM's module-map generation and fails on the
  `CEngine` target.
- `BestBallEngine.assignSlots` (and therefore `lineup` and `totals`) delegates to
  the engine, so who starts is decided once for both apps. The slot table stays
  in `Lineup.swift` because the waiver and trade searches walk eligibility
  locally while they explore packages; only the scoring is shared.
