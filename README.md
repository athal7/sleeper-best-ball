# 🏈 Sleeper Best Ball

A simple Streamlit app that projects fantasy football matchup scores for best ball leagues

Sleeper currently prioritizes scored points over future player projections, even if those projections are higher, causing a misleading projected score and winner. 

This app provides optimistic projections, leveraging https://github.com/dtsong/sleeper-api-wrapper to query the sleeper API, and is available for use at  https://sleeper-best-ball.streamlit.app/

The Waiver Guide groups lineup-improving adds by the player to drop. Trade Suggestions groups win-win offers by partner and considers 1-for-1, 1-for-2, 2-for-1, and 2-for-2 trades. Every 1-for-1 is evaluated; two-player packages use each roster's eight highest-projected candidates. Uneven trades may require a roster spot. Player names open Sleeper web profiles.