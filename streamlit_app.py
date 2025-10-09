import streamlit as st
import pandas as pd
from sleeper_wrapper import League, User, get_sport_state
import data
import display

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
    st.markdown(f"#### Week {week}")

for league_id in leagues:
    league = League(league_id)
    st.markdown(f"###### {league.get_league_name()}")

    df = data.rosters(season, week, league)
    positions = data.starting_positions(league)

    df['spos'] = None
    for fantasy_team in df['fantasy_team'].unique():
        for spos, eligible in positions.iterrows():
            starter = df.loc[(df['fantasy_team'] == fantasy_team) & (df['position'].isin(eligible['eligible'])) & (
                df['spos'].isnull()), 'spos'].head(1).index
            df.loc[starter, 'spos'] = spos

    df = df[df['spos'].notnull()]
    df['name'] = df.apply(display.player_name, axis=1)
    df['score'] = df.apply(display.score, axis=1)

    for matchup_id, players in df.groupby('matchup_id'):
        if not locked_league_id and username and username not in players['fantasy_team'].values:
            continue

        (t1_name, t1_players), (t2_name, t2_players) = players.groupby('fantasy_team')

        matchup = positions.copy()[[]]

        matchup = matchup.join(t1_players.set_index('spos')[['name', 'score']], how='left').rename(columns={'name': t1_name, 'score': display.team_score(t1_players)})

        matchup = matchup.join(t2_players.set_index('spos')[['score', 'name']], how='left', rsuffix='_2').rename(columns={'name': t2_name, 'score': display.team_score(t2_players)})

        matchup
        
    st.text("* projected")

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
