# 🏈 Sleeper Best Ball

A simple Streamlit app that projects fantasy football matchup scores for best ball leagues

Sleeper currently prioritizes scored points over future player projections, even if those projections are higher, causing a misleading projected score and winner. 

This app provides optimistic projections, leveraging https://github.com/dtsong/sleeper-api-wrapper to query the sleeper API, and is available for use at  https://sleeper-best-ball.streamlit.app/

Live Scores keeps rostered players even when Sleeper lists no NFL team for them. Entries with no usable player metadata are omitted rather than assigned invented positions or points.

The Waiver Guide considers dropping any rostered player, regardless of position, and groups adds that improve the lineup by more than 1 projected point per week on average under the best player to drop. It shows the five highest-ranked adds for each drop. Trade Suggestions groups win-win offers by partner and considers 1-for-1, 1-for-2, 2-for-1, and 2-for-2 trades. Each team must gain more than 1 projected point per week on average (with playoff weeks weighted more heavily). Both tools score only from the selected current week through the league’s championship week, including custom playoff lengths and multiweek rounds. Every 1-for-1 is evaluated; two-player packages use each roster's eight highest-projected candidates. Uneven trades may require a roster spot. Its trade analyzer takes any two teams plus an optional position need for each and lists every offer that improves both of them by any amount. Player names open Sleeper web profiles.

Draft, waiver, and trade recommendations share raw season projections across users and apply league scoring settings per request. Live matchup projections reuse the same weekly raw data. Scored weekly projection inputs are reused for identical seasons and scoring settings until the hourly projection refresh. Projection caches refresh at each hour boundary; the first season load still fetches all 18 regular-season weeks.

## 📱 iOS app and widget

The `ios/` folder contains a native SwiftUI app and a Home Screen widget that show the same optimistic projections and best-ball lineups as the Streamlit app.

- Connect with a Sleeper username, pick a league, and browse weeks 1–18.
- Each matchup shows every roster's best-ball lineup, current points, optimistic projection, and live game state.
- The widget refreshes from Sleeper about every 30 minutes and falls back to the last snapshot saved by the app.

Open `ios/BestBall.xcodeproj` in Xcode 15 or newer and run the `BestBall` scheme (iOS 17+), choosing your Apple ID team under Signing & Capabilities.

A free Apple ID is enough to install on your own iPhone: the build lasts seven days before you re-run it from Xcode. Free teams cannot use App Groups, so the project ships without that capability and the widget stays on its "open the app" placeholder.

To let the widget share the selected league, join the paid Developer Program and add the App Group `group.$(BB_BUNDLE_ID)` to both targets in Xcode. `SharedStore` picks the group up through the `BBAppGroup` Info.plist key and falls back to standard defaults when the group is unavailable.

`BB_BUNDLE_ID` is a project build setting (default `com.sleeperbestball.app`); change it if that identifier is already taken, since free teams can only sign identifiers nobody else has claimed.

The app starts a Live Activity for the current week's matchup in **every in-season league** when you open it, each showing both sides' live and projected points on the Lock Screen and in the Dynamic Island. They update every time the app refreshes (no push server involved), and the bolt button in the toolbar stops all of them until you turn them back on. iOS only keeps a handful of Live Activities alive at once, so tracking is capped at the first five in-season leagues. Live Activities need no App Group, so they work on a free team.

Your Sleeper username is remembered at the account level, so changing leagues doesn't make you retype it — and the leagues you're in are loaded as soon as the app opens.

Projection and lineup logic lives in the `ios/BestBallKit` Swift package and has no dependency on SwiftUI, so it can be tested from the command line:

```bash
cd ios/BestBallKit
swift test
```

The waiver guide, trade tools, and draft assistant are not part of the iOS app yet.