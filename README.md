# 🏈 Sleeper Best Ball

A simple Streamlit app that projects fantasy football matchup scores for best ball leagues

Sleeper currently prioritizes scored points over future player projections, even if those projections are higher, causing a misleading projected score and winner. 

This app provides optimistic projections, leveraging https://github.com/dtsong/sleeper-api-wrapper to query the sleeper API, and is available for use at  https://sleeper-best-ball.streamlit.app/

The Waiver Guide considers dropping any rostered player, regardless of position, and groups lineup-improving adds by the best player to drop. Trade Suggestions groups win-win offers by partner and considers 1-for-1, 1-for-2, 2-for-1, and 2-for-2 trades. Each team must gain more than 1 projected point per week on average (with playoff weeks weighted more heavily). Every 1-for-1 is evaluated; two-player packages use each roster's eight highest-projected candidates. Uneven trades may require a roster spot. Player names open Sleeper web profiles.

Draft, waiver, and trade recommendations share raw season projections across users and apply league scoring settings per request. Live matchup projections reuse the same weekly raw data. Projection caches refresh at each hour boundary; the first season load still fetches all 18 regular-season weeks.