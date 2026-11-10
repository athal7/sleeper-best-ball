# 🏈 Sleeper Best Ball

A simple Streamlit app that projects fantasy football matchup scores for best ball leagues

Sleeper currently prioritizes scored points over future player projections, even if those projections are higher, causing a misleading projected score and winner. 

This app provides optimistic projections, leveraging https://github.com/dtsong/sleeper-api-wrapper to query the sleeper API, and is available for use at  https://sleeper-best-ball.streamlit.app/

Live Scores keeps rostered players even when Sleeper lists no NFL team for them. Entries with no usable player metadata are omitted rather than assigned invented positions or points.

The Waiver Guide considers dropping any rostered player, regardless of position, and groups adds that improve the lineup by more than 1 projected point per week on average under the best player to drop. It shows the five highest-ranked adds for each drop. Trade Suggestions groups win-win offers by partner and considers 1-for-1, 1-for-2, 2-for-1, and 2-for-2 trades. Each team must gain more than 1 projected point per week on average (with playoff weeks weighted more heavily). Both tools score only from the selected current week through the league’s championship week, including custom playoff lengths and multiweek rounds. Every 1-for-1 is evaluated; two-player packages use each roster's eight highest-projected candidates. Uneven trades may require a roster spot. Its trade analyzer takes any two teams plus an optional position need for each and lists every offer that improves both of them by any amount. Player names open Sleeper web profiles.

Draft, waiver, and trade recommendations share raw season projections across users and apply league scoring settings per request. Live matchup projections reuse the same weekly raw data. Scored weekly projection inputs are reused for identical seasons and scoring settings until the hourly projection refresh. Projection caches refresh at each hour boundary; the first season load still fetches all 18 regular-season weeks.