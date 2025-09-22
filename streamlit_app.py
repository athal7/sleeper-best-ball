import streamlit as st
import pandas as pd
from sleeper_wrapper import League, User, Stats, Players
from datetime import datetime
import requests

st.title("Sleeper Best Ball Outcome Predictor 🏈")

league_id = st.query_params.get('league', None)
week = st.query_params.get('week', None)
season = int(st.query_params.get('season', datetime.now().year))

if league_id is None:
    username = st.text_input("Enter your Sleeper username:")
    if username:
        user = User(username)
        leagues = user.get_all_leagues('nfl', season)
        if leagues:
            selected_league_id = st.selectbox(
                "Select a league:",
                leagues,
                format_func=lambda l: l['name'])['league_id']
            if selected_league_id:
                if st.button("Select this league"):
                    st.query_params.league = selected_league_id
                    st.rerun()
        else:
            st.warning("No leagues found for this user.")
else:
    league = League(league_id)
    st.subheader(league.get_league_name())
    st.write(f"League ID: {league_id}")
    if week is None:
        selected_week = st.number_input("Enter the week number:",
                                min_value=1, max_value=18, value=int(week or 1))
        if st.button("Set Week"):
            st.query_params.week = selected_week
            st.rerun()
    else:
        st.write(f"Week {week}")
        stats = Stats()
        week_stats = stats.get_week_stats("regular", season, int(week))
        week_projections = stats.get_week_projections("regular", season, int(week))
    
        matchups = league.get_matchups(week)
        players = Players().get_all_players("nfl")
        users = league.get_users()
        

        player_rows = [ ]       
        for matchup in matchups:
            for player_id, points in matchup['players_points'].items():
                player = players.get(player_id, {})
                player_stats = week_stats.get(player_id, {})
                player_rows.append({
                    "player_id": player_id,
                    "player_name": player.get('full_name'),
                    "position": player.get('position'),
                    "roster_id": matchup['roster_id'],
                    "matchup_id": matchup['matchup_id'],
                    "points": points,
                    "ppr_points": player_stats.get('pts_ppr'),
                    "projection": week_projections.get(player_id, {}).get('pts_ppr'),
                    "game_played": player_stats.get('gp', 0),
                })
        
        st.dataframe(pd.DataFrame(player_rows))