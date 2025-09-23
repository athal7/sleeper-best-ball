import streamlit as st
import pandas as pd
from sleeper_wrapper import League, User, Stats, Players
import nfl_data_py as nfl
from datetime import datetime
import utils

st.title("Sleeper Best Ball 🏈")
season = int(st.query_params.get('season', datetime.now().year))
schedule = nfl.import_schedules([season])

username = st.session_state.get('username')
locked_league_id = st.query_params.get('league')
league_id = st.session_state.get('league', {}).get('league_id') or locked_league_id
week = st.session_state.get('selected_week', utils.current_week(schedule))


if locked_league_id is None:
    st.text_input("Enter your Sleeper username:", key='username')

    if username and not locked_league_id:
        user = User(username)
        leagues = user.get_all_leagues('nfl', season)
        if leagues:
            st.selectbox(
                "Select a league:",
                leagues,
                format_func=lambda l: l['name'], 
                key='league')
        else:
            st.warning("No leagues found for this user.")


if league_id:
    league = League(league_id)
    st.subheader(league.get_league_name())
    st.write(f"League ID: {league_id}")

    st.number_input("Enter the week number:", min_value=1, max_value=18,
                    value=week, key="selected_week")
    stats = Stats()
    week_projections = stats.get_week_projections("regular", season, week)

    matchups = league.get_matchups(week)
    all_players = Players().get_all_players("nfl")
    rosters = league.get_rosters()
    users = league.get_users()

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
            player_projection = week_projections.get(player_id, {})
            projection = player_projection.get('pts_ppr')
            if player['position'] == 'TE' and projection is not None:
                projection += player_projection.get('rec', 0) * 0.5
            players.append({
                "player_id": player_id,
                "player_name": player['full_name'],
                "user_id": user_id,
                "position": player.get('position'),
                "points": points,
                "projection": projection,
                "game_played": utils.is_game_over(schedule, week, player.get('team'))
            })

    players_df = pd.DataFrame(players)
    users_df = pd.DataFrame(users)
    st.header("Matchups")
    for matchup_id, user_ids in matchup_dict.items():
        # Only support 2-team matchups for this table format
        if len(user_ids) != 2:
            st.warning("Only 2-team matchups are supported for this view.")
            continue

        team_dfs = []
        team_names = []
        team_scores = []
        starters_list = []
        for user_id in user_ids:
            team_df = players_df[players_df['user_id'] == user_id]
            optimistic_score, starters = utils.calculate_optimistic_starters(
                team_df)
            user_display_name = users_df.loc[users_df['user_id']
                                             == user_id, 'display_name'].values[0]
            team_dfs.append(pd.DataFrame(starters)[
                            ['position', 'player_name', 'optimistic', 'points']])
            team_names.append(user_display_name)
            team_scores.append(optimistic_score)
            starters_list.append(starters)

        # Build table rows in the order of starters for each team
        max_starters = max(len(starters_list[0]), len(starters_list[1]))
        table_rows = []
        for i in range(max_starters):
            row = []
            for team_idx in range(2):
                if i < len(starters_list[team_idx]):
                    starter = starters_list[team_idx][i]
                    player = starter['player_name']
                    proj = starter['optimistic']
                    pts = starter['points']
                    pos = starter['position']
                else:
                    player, proj, pts, pos = '', '', '', ''
                row.extend(
                    [player, f"{proj:.2f}" if proj != '' else '', f"{pts:.2f}" if pts != '' else ''])
            # Insert position from first team (or second if first is empty)
            row.insert(3, starters_list[0][i]['position'] if i < len(starters_list[0]) else (
                starters_list[1][i]['position'] if i < len(starters_list[1]) else ''))
            table_rows.append(row)

        # Build HTML table
        html = "<table style='width:100%; border-collapse:collapse;'>"
        # Top row: team names and scores, spanning 3 columns each
        html += "<tr>"
        html += f"<th colspan='3' style='text-align:center;'>{team_names[0]}<br><span style='font-weight:normal;'>Projected: {team_scores[0]:.2f}</span></th>"
        html += "<th></th>"
        html += f"<th colspan='3' style='text-align:center;'>{team_names[1]}<br><span style='font-weight:normal;'>Projected: {team_scores[1]:.2f}</span></th>"
        html += "</tr>"
        # Table body, no header
        for row in table_rows:
            html += "<tr>"
            for i, cell in enumerate(row):
                style = "padding:4px; border:1px solid #ddd;"
                # Highlight if projection != points
                if i in [2, 6] and row[i] != row[i-1] and row[i] != '':
                    style += "background-color:#ffeeba;"
                html += f"<td style='{style}'>{cell}</td>"
            html += "</tr>"
        html += "</table>"

        st.markdown(html, unsafe_allow_html=True)
