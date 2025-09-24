import streamlit as st
import pandas as pd
from sleeper_wrapper import League, User, Stats, Players
import nfl_data_py as nfl
from datetime import datetime

st.title("Sleeper Best Ball 🏈")
season = int(st.query_params.get('season', datetime.now().year))


username = st.session_state.get('username')
locked_league_id = st.query_params.get('league')
league_id = st.session_state.get('league', {}).get(
    'league_id') or locked_league_id


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
    users = pd.DataFrame(league.get_users()).set_index('user_id')[[
        'display_name']]
    rosters = pd.DataFrame(league.get_rosters()).set_index(
        'roster_id').join(users, on='owner_id')
    stats = Stats()

    all_players = pd.DataFrame.from_dict(
        Players().get_all_players("nfl"), orient='index')[['team', 'first_name', 'last_name', 'position']]
    schedule = pd.DataFrame(nfl.import_schedules([season]))
    week = st.session_state.get(
        'selected_week', schedule[schedule['result'].isnull()]['week'].min())
    projections = pd.DataFrame.from_dict(
        stats.get_week_projections("regular", season, week), orient='index')

    st.subheader(league.get_league_name())
    st.write(f"League ID: {league_id}")
    st.number_input("Enter the week number:", min_value=1, max_value=18,
                    value=week, key="selected_week")

    df = pd.DataFrame(league.get_matchups(week)).explode('players').rename(
        columns={'players': 'player_id'}).set_index('player_id')
    df['points'] = df.apply(
        lambda row: row['players_points'].get(row.name, None), axis=1)
    df = df[['points', 'roster_id', 'matchup_id']]
    df = df.join(all_players, how='left')
    df['game_played'] = False
    df['game_played'] = df.apply(lambda row: schedule.loc[(schedule['season'] == season) & (schedule['week'] == week) & (
        (schedule['home_team'] == row['team']) | (schedule['away_team'] == row['team']))]['result'].notnull().values, axis=1).astype(bool)
    df['projection'] = projections['pts_ppr']
    df.loc[df['position'] == 'TE',
           'projection'] += projections['rec'] * 0.5
    df['optimistic'] = df.apply(
        lambda row: row['points'] if (
            hasattr(row['game_played'],
                    'size') and row['game_played'] and row['points']
        ) else max(row['points'] or 0.0, row['projection'] or 0.0),
        axis=1
    )
    df = df.sort_values('optimistic', ascending=False)

    st.header("Matchups")
    for roster_id in df['roster_id'].unique():
        qb = df[(df['roster_id'] == roster_id) &
                (df['position'] == 'QB')].head(1)
        df.loc[qb.index, 'spos'] = 'QB'

        rbs = df[(df['roster_id'] == roster_id) &
                 (df['position'] == 'RB')].head(3)
        df.loc[rbs.index, 'spos'] = ['RB1', 'RB2', 'RB3'][:len(rbs)]

        wrs = df[(df['roster_id'] == roster_id) &
                 (df['position'] == 'WR')].head(3)
        df.loc[wrs.index, 'spos'] = ['WR1', 'WR2', 'WR3'][:len(wrs)]

        tes = df[(df['roster_id'] == roster_id) &
                 (df['position'] == 'TE')].head(2)
        df.loc[tes.index, 'spos'] = ['TE1', 'TE2'][:len(tes)]

        flex = df[
            (df['roster_id'] == roster_id) &
            (df['position'].isin(['RB', 'WR', 'TE'])) &
            (df['spos'].isnull())].head(1)
        df.loc[flex.index, 'spos'] = 'FLEX'

        sflex = df[(df['roster_id'] == roster_id) &
                   (df['spos'].isnull())].head(1)
        df.loc[sflex.index, 'spos'] = 'SFLEX'

    matchups = df['matchup_id'].nunique()
    starters = ['QB', 'RB1', 'RB2', 'RB3', 'WR1',
                'WR2', 'WR3', 'TE1', 'TE2', 'FLEX', 'SFLEX']

    def player_name(row):
        return f"{row['first_name'][0]}. {row['last_name']}"

    def score(row):
        if row['game_played']:
            return f"{row['optimistic']:.2f}"
        else:
            return f"<em>{row['optimistic']:.2f}</em>"

    def team_name(team_id):
        return rosters.loc[team_id, 'display_name']

    def team_score(team_id):
        return df[(df['roster_id'] == team_id) & (df['spos'].notnull())]['optimistic'].sum()

    for matchup in range(1, matchups + 1):
        team1, team2 = df[df['matchup_id'] == matchup]['roster_id'].unique()
        html = "<table style='width: 100%; max-width: 800px'><thead><tr>"
        html += f"<th>{team_name(team1)}</th>"
        html += f"<th>{team_score(team1):.2f}</th>"
        html += "<th></th>"
        html += f"<th>{team_name(team2)}</th>"
        html += f"<th>{team_score(team2):.2f}</th>"
        html += "</tr></thead><tbody>"

        for pos in starters:
            p1 = df[(df['roster_id'] == team1) & (
                df['spos'] == pos)].iloc[0].to_dict()
            p2 = df[(df['roster_id'] == team2) & (
                df['spos'] == pos)].iloc[0].to_dict()
            html += "<tr>"
            html += f"<td>{player_name(p1)}</td>"
            html += f"<td>{score(p1)}</td>"
            html += f"<td align='center'>{pos}</td>"
            html += f"<td>{score(p2)}</td>"
            html += f"<td>{player_name(p2)}</td>"
            html += "</tr>"
        html += "</tbody></table>"
        st.markdown(html, unsafe_allow_html=True)
