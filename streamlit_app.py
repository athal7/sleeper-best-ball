import streamlit as st
import pandas as pd
from sleeper_wrapper import League, User, Stats, Players
from datetime import datetime

st.title("Sleeper Best Ball Outcome Predictor 🏈")

league_id = st.query_params.get('league', None)
week = int(st.query_params.get('week', 1))
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
    def set_week():
        st.query_params.week = st.session_state.selected_week
    st.number_input("Enter the week number:", min_value=1, max_value=18, value=week, on_change=set_week, key="selected_week")
    stats = Stats()
    week_stats = stats.get_week_stats("regular", season, week)
    week_projections = stats.get_week_projections("regular", season, week)
    
    matchups = league.get_matchups(week)    
    all_players = Players().get_all_players("nfl")
    rosters = league.get_rosters()
    users = league.get_users()
        
    def get_optimistic_score(df):
        # Only consider players who played or have a projection
        df = df.copy()
        df['optimistic'] = df.apply(
            lambda row: row['points'] if row['game_played'] else row['projection'], axis=1
            )
        df = df[df['optimistic'].notnull()]
        # Split by position
        qbs = df[df['position'] == 'QB'].sort_values('optimistic', ascending=False)
        rbs = df[df['position'] == 'RB'].sort_values('optimistic', ascending=False)
        wrs = df[df['position'] == 'WR'].sort_values('optimistic', ascending=False)
        tes = df[df['position'] == 'TE'].sort_values('optimistic', ascending=False)
        flex = df[df['position'].isin(['RB', 'WR', 'TE'])].sort_values('optimistic', ascending=False)
        superflex = df.sort_values('optimistic', ascending=False)

        starters = []
            # 1 QB
        starters += qbs.head(1).to_dict('records')
            # 3 RB
        starters += rbs.head(3).to_dict('records')
            # 3 WR
        starters += wrs.head(3).to_dict('records')
            # 2 TE
        starters += tes.head(2).to_dict('records')
            # 1 RB/WR/TE FLEX (not already counted)
        used_ids = {p['player_id'] for p in starters}
        flex_avail = flex[~flex['player_id'].isin(used_ids)]
        starters += flex_avail.head(1).to_dict('records')
        used_ids = {p['player_id'] for p in starters}
            # 1 SUPERFLEX (QB/RB/WR/TE, not already counted)
        superflex_avail = superflex[~superflex['player_id'].isin(used_ids)]
        starters += superflex_avail.head(1).to_dict('records')
            # Calculate total
        total = sum(p['optimistic'] for p in starters if p['optimistic'] is not None)
        return total, starters
        
    players = []
    matchup_dict = {}
    for matchup in matchups:
        matchup_id = matchup['matchup_id']
        user_id = rosters[matchup['roster_id']-1].get("owner_id")
        if matchup_id not in matchup_dict:
            matchup_dict[matchup_id] = []
        matchup_dict[matchup_id].append(user_id)
        for player_id, points in matchup['players_points'].items():
            player = all_players.get(player_id, {})
            player_stats = week_stats.get(player_id, {})
            players.append({
                    "player_id": player_id,
                    "player_name": player['full_name'],
                    "user_id": user_id,
                    "position": player.get('position'),
                    "points": points,
                    "projection": week_projections.get(player_id, {}).get('pts_ppr'),
                    "game_played": player_stats.get('gp', 0),
                })
                
    players_df = pd.DataFrame(players)
    users_df = pd.DataFrame(users)
    st.header("Matchups")
    for matchup_id, user_ids in matchup_dict.items():
        cols = st.columns(len(user_ids))
        for idx, user_id in enumerate(user_ids):
            team_df = players_df[players_df['user_id'] == user_id]
            optimistic_score, starters = get_optimistic_score(team_df)
            user_display_name = users_df.loc[users_df['user_id'] == user_id, 'display_name'].values[0]
            cols[idx].markdown(f"**{user_display_name}**")
            cols[idx].write(f"Projected Score: **{optimistic_score:.2f}**")
            cols[idx].dataframe(pd.DataFrame(starters)[['player_name', 'position', 'optimistic', 'points']].rename(columns={'optimistic': 'projection'}))
        