import streamlit as st
import pandas as pd
from sleeper_wrapper import League, User, Stats, Players, get_sport_state
import nflreadpy as nfl
from nflreadpy.config import update_config

update_config(cache_mode="off")

st.title("Sleeper Best Ball 🏈")
st.markdown(
    "*Sleeper predictions are misleading for best ball scoring, so I built this app*")
current = get_sport_state('nfl')
season = int(current['league_season'])
week = int(current['display_week'])

username = st.query_params.get('username')
locked_league_id = st.query_params.get('league')
leagues = []

if locked_league_id:
    leagues = [locked_league_id]
else:
    st.text_input("Enter your Sleeper username:", key='username_input',
                  on_change=lambda: st.query_params.update({'username': st.session_state.username_input}), value=username)

    if username and not locked_league_id:
        user = User(username)
        leagues = [l['league_id'] for l in user.get_all_leagues('nfl', season)]
        if not leagues:
            st.warning("No leagues found for this user.")

if leagues:
    st.write(f"#### Week {week}")

for league_id in leagues:
    league = League(league_id)
    league_info = league.get_league()
    st.write(f"###### {league_info['name']}")

    users = pd.DataFrame(league.get_users()).set_index('user_id')[[
        'display_name']]
    rosters = pd.DataFrame(league.get_rosters()).set_index(
        'roster_id').join(users, on='owner_id')
    stats = Stats()

    all_players = pd.DataFrame.from_dict(
        Players().get_all_players("nfl"), orient='index')[['team', 'first_name', 'last_name', 'position']]
    pbp = pd.DataFrame(nfl.load_pbp(season).to_pandas())
    projections = pd.DataFrame.from_dict(
        stats.get_week_projections("regular", season, week), orient='index')

    df = pd.DataFrame(league.get_matchups(week)).explode('players').rename(
        columns={'players': 'player_id'}).set_index('player_id')
    df['points'] = df.apply(
        lambda row: row['players_points'].get(row.name, None), axis=1)
    df = df[['points', 'roster_id', 'matchup_id']]
    df = df.join(all_players, how='left')

    TOTAL_MINS = 60
    def minutes_remaining(row):
        team = row['team']
        if team == "LAR":
            team = "LA"
        game = pbp.loc[(pbp['week'] == week) & (
            (pbp['home_team'] == team) | (pbp['away_team'] == team))]
        if game.empty:
            return TOTAL_MINS
        else:
            return int(game['game_seconds_remaining'].min() / 60.0)
    df['minutes_remaining'] = df.apply(minutes_remaining, axis=1)

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
        if row['minutes_remaining'] <= 0:
            return row['points']
        elif row['minutes_remaining'] >= TOTAL_MINS:
            return row['projection'] if row['projection'] is not None else 0.0
        else:
            return row['points'] + (row['points'] * row['minutes_remaining'] / TOTAL_MINS) 
    df['optimistic'] = df.apply(optimistic_score, axis=1)
    df = df.sort_values('optimistic', ascending=False)

    positions = [
        ['QB', ['QB']],
        ['RB', ['RB']],
        ['WR', ['WR']],
        ['TE', ['TE']],
        ['FLEX', ['RB', 'WR', 'TE']],
        ['SUPER_FLEX', ['QB', 'RB', 'WR', 'TE']],
        ['K', ['K']],
        ['DEF', ['DEF']]
    ]
    positions = pd.DataFrame(
        positions, columns=['position', 'eligible_positions']).set_index('position')

    def make_starting_positions(row):
        pos = row.name
        cnt = league_info['roster_positions'].count(pos)
        if cnt == 1:
            return [pos]
        else:
            return [f"{pos}{i+1}" for i in range(cnt)]
    positions['starting_positions'] = positions.apply(
        make_starting_positions, axis=1)

    positions = positions.explode('starting_positions')
    positions = positions[positions['starting_positions'].notnull()].set_index(
        'starting_positions')

    df['spos'] = None
    for roster_id in df['roster_id'].unique():
        for spos, eligible in positions.iterrows():
            starter = df.loc[(df['roster_id'] == roster_id) & (df['position'].isin(eligible['eligible_positions'])) & (
                df['spos'].isnull()), 'spos'].head(1).index
            df.loc[starter, 'spos'] = spos

    df = df[df['spos'].notnull()]

    def player_name(row):
        return f"{row['first_name'][0]}. {row['last_name']}"

    def score(row):
        score = f"{row['optimistic']:.2f}"
        if row['minutes_remaining'] > 0:
            score += "*"
        return score

    def team_name(team_id):
        return rosters.loc[team_id, 'display_name']

    def team_score(team_id):
        starters = df[(df['roster_id'] == team_id) & (df['spos'].notnull())]
        score = f"{starters['optimistic'].sum():.2f}"
        if not starters['minutes_remaining'].le(0).all():
            score += "*"
        return score

    matchups = df['matchup_id'].nunique()
    starters = positions.index.tolist()
    for matchup in range(1, matchups + 1):
        team1, team2 = df[df['matchup_id'] == matchup]['roster_id'].unique()
        if not locked_league_id and username and username not in [team_name(team1), team_name(team2)]:
            continue
        headers = [
            team_name(team1),
            team_score(team1),
            team_score(team2),
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
        matchup_df = pd.DataFrame(table_data, columns=headers, index=starters).rename(
            index={'SUPER_FLEX': 'SFLEX'})
        matchup_df
        st.html("<small style='display:block;float:right;margin-top:0;padding-top:0;margin-bottom:30px;'>* projected</small>")
    if not locked_league_id:
        st.button("View League Matchups", on_click=lambda: st.query_params.update(
            {'league': league_id}))
    elif username:
        st.button("View My Matchups",
                  on_click=lambda: st.query_params.pop('league', None))
    st.divider()
    st.link_button("Submit Feedback",
                   "https://github.com/athal7/sleeper-best-ball/issues", icon="✉️")
    st.link_button("Buy Me A Coffee",
                   "https://buymeacoffee.com/s4m9knqt9vb", icon="☕")
