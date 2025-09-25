import streamlit as st
import pandas as pd
from sleeper_wrapper import League, User, Stats, Players, get_sport_state
import nfl_data_py as nfl
from streamlit_extras import buy_me_a_coffee

st.title("Sleeper Best Ball 🏈")
current = get_sport_state('nfl')
season = int(current['league_season'])
week = int(current['display_week'])

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
    league_info = league.get_league()
    scoring = league_info['scoring_settings']

    users = pd.DataFrame(league.get_users()).set_index('user_id')[[
        'display_name']]
    rosters = pd.DataFrame(league.get_rosters()).set_index(
        'roster_id').join(users, on='owner_id')
    stats = Stats()

    all_players = pd.DataFrame.from_dict(
        Players().get_all_players("nfl"), orient='index')[['team', 'first_name', 'last_name', 'position']]
    schedule = pd.DataFrame(nfl.import_schedules([season]))
    projections = pd.DataFrame.from_dict(
        stats.get_week_projections("regular", season, week), orient='index')
    st.subheader(league.get_league_name())
    st.write(f"League ID: {league_id}")

    df = pd.DataFrame(league.get_matchups(week)).explode('players').rename(
        columns={'players': 'player_id'}).set_index('player_id')
    df['points'] = df.apply(
        lambda row: row['players_points'].get(row.name, None), axis=1)
    df = df[['points', 'roster_id', 'matchup_id']]
    df = df.join(all_players, how='left')
    df['game_played'] = False

    def game(row):
        team = row['team']
        if team == "LAR":
            team = "LA"
        game = schedule.loc[(schedule['season'] == season) & (schedule['week'] == week) & (
            (schedule['home_team'] == team) | (schedule['away_team'] == team))]
        if not game.empty:
            return game['result'].notnull().values[0]
        return False
    df['game_played'] = df.apply(game, axis=1)

    def compute_projection(row):
        pid = row.name
        if pid not in projections.index:
            return None
        proj = projections.loc[pid]
        total = 0.0
        for stat, pts in league_info['scoring_settings'].items():
            if stat in proj and pd.notnull(proj[stat]):
                total += proj[stat] * pts
        return total if total != 0.0 else None

    df['projection'] = df.apply(compute_projection, axis=1)

    def optimistic_score(row):
        if row['game_played'] and row['points'] is not None:
            return row['points']
        elif row['projection'] is not None:
            return row['projection']
        else:
            return 0.0
    df['optimistic'] = df.apply(optimistic_score, axis=1)
    df = df.sort_values('optimistic', ascending=False)

    st.header(f"Week {week} Matchups")
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
            return f"*{row['optimistic']:.2f}*"

    def team_name(team_id):
        return rosters.loc[team_id, 'display_name']

    def team_score(team_id):
        return df[(df['roster_id'] == team_id) & (df['spos'].notnull())]['optimistic'].sum()

    for matchup in range(1, matchups + 1):
        team1, team2 = df[df['matchup_id'] == matchup]['roster_id'].unique()
        headers = [
            team_name(team1),
            f"{team_score(team1):.2f}",
            f"{team_score(team2):.2f}",
            team_name(team2)
        ]
        table_data = []
        for pos in starters:
            p1 = df[(df['roster_id'] == team1) & (
                df['spos'] == pos)].iloc[0].to_dict()
            p2 = df[(df['roster_id'] == team2) & (
                df['spos'] == pos)].iloc[0].to_dict()
            table_data.append([
                player_name(p1),
                score(p1),
                score(p2),
                player_name(p2)
            ])
        matchup_df = pd.DataFrame(table_data, columns=headers, index=starters)
        st.table(matchup_df)
    buy_me_a_coffee.button(username='athal7', floating=False)
