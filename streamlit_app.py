import streamlit as st
import pandas as pd
from sleeper_wrapper import League, User, get_sport_state, Stats, Players, League
import requests
from dataclasses import dataclass

def player_name(row):
    return f"{row['first_name'][0]}. {row['last_name']}"

def score(row):
    score = f"{row['points']:.2f}"
    if row['projected']:
        score += "*"
    return score

def team_score(team):
    score = f"{team['points'].sum():.2f}"
    if team['projected'].any():
        score += "*"
    return score


team_mappings = {
    'WSH': 'WAS',
}
position_mappings = pd.DataFrame([
    ['QB', 'QB', ['QB']],
    ['RB', 'RB', ['RB']],
    ['WR', 'WR', ['WR']],
    ['TE', 'TE', ['TE']],
    ['FLEX', 'FLEX', ['RB', 'WR', 'TE']],
    ['SUPER_FLEX', 'SFLEX', ['QB', 'RB', 'WR', 'TE']],
    ['K', 'K', ['K']],
    ['DEF', 'DEF', ['DEF']]
]).rename(columns={1: 'position', 2: 'eligible'}).set_index(0)


def _game_statuses(season: int, week: int):
    url = f"https://partners.api.espn.com/v2/sports/football/nfl/events?limit=50&season={season}&week={week}"
    resp = requests.get(url)
    data = resp.json()
    df =pd.json_normalize([e['competitions'][0]
                           for e in data['events']])
    df = df.explode('competitors')
    df['team'] = df['competitors'].apply(lambda x: x['team']['abbreviation'])
    df['team'] = df['team'].replace(team_mappings)
    df.set_index('team', inplace=True)
    return df[['status.period', 'status.clock']]

def _projection(scoring: dict):
    def _compute(row):
        total = 0.0
        for stat, pts in scoring.items():
            if stat in row and pd.notnull(row[stat]):
                total += row[stat] * pts
        return total
    return _compute


def _optimistic_score(row):
    if pd.isna(row['pct_played']):
        return 0

    return row['points'] + (1 - row['pct_played']) * row['projection']

@dataclass
class Data:
    _game_statuses: pd.DataFrame = None
    _matchups: pd.DataFrame = None
    _rosters: pd.DataFrame = None
    _users: pd.DataFrame = None
    _players: pd.DataFrame = None
    _projections: pd.DataFrame = None
    _scoring: dict = None
    _positions: list[str] = None

    @staticmethod
    def from_league(league: League, season: int, week: int):
        return Data(
            _game_statuses=_game_statuses(season, week),
            _matchups=pd.DataFrame(league.get_matchups(week)),
            _rosters=pd.DataFrame(league.get_rosters()).set_index('roster_id')[['owner_id']],
            _users=pd.DataFrame(league.get_users()).set_index('user_id')[['display_name']],
            _players=pd.DataFrame.from_dict(
                Players().get_all_players("nfl"), orient='index')[['team', 'first_name', 'last_name', 'position']],
            _projections=pd.DataFrame.from_dict(
                Stats().get_week_projections("regular", season, week), orient='index'),
            _scoring=league.get_league()['scoring_settings'],
            _positions=league.get_league()['roster_positions']
        )


    def rosters(self):
        df = self._matchups
        df = df.explode('players').rename(
            columns={'players': 'player_id'}).set_index('player_id')
        df['points'] = df.apply(
            lambda row: row['players_points'].get(row.name, None), axis=1)
        df = df[['points', 'roster_id', 'matchup_id']]
        df = df.join(self._rosters, on='roster_id', how='left')
        df = df.join(self._users.rename(columns={'display_name': 'fantasy_team'}), on='owner_id', how='left')
        df = df.join(self._players, how='left')
        df = df.join(self._game_statuses, on='team', how='left')
        df = df.join(self._projections, on=df.index, how='left')

        df['pct_played'] = (df['status.period'] * 15 - df['status.clock'] / 60) / 60
        df['projection'] = df.apply(_projection(self._scoring), axis=1)
        df['points'] = df.apply(_optimistic_score, axis=1)
        df['projected'] = df['pct_played'].apply(
            lambda x: x < 1 if pd.notnull(x) else False)

        return df.sort_values('points', ascending=False)[['first_name', 'last_name', 'team', 'position', 'points', 'fantasy_team', 'matchup_id', 'projected']]


    def starting_positions(self):
        df = position_mappings.copy()
        df = df.join(pd.Series(self._positions).value_counts(), how='inner')
        df = df.loc[df.index.repeat(df['count'])].reset_index(drop=True)
        df['position'] = df['position'] + \
            (df.groupby('position').cumcount() + 1).astype(str)
        df.set_index('position', inplace=True)
        return df[['eligible']]


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

    data = Data.from_league(league, season, week)
    df = data.rosters()
    positions = data.starting_positions()

    df['spos'] = None
    for fantasy_team in df['fantasy_team'].unique():
        for spos, eligible in positions.iterrows():
            starter = df.loc[(df['fantasy_team'] == fantasy_team) & (df['position'].isin(eligible['eligible'])) & (
                df['spos'].isnull()), 'spos'].head(1).index
            df.loc[starter, 'spos'] = spos

    df = df[df['spos'].notnull()]
    df['name'] = df.apply(player_name, axis=1)
    df['score'] = df.apply(score, axis=1)

    for matchup_id, players in df.groupby('matchup_id'):
        if not locked_league_id and username and username not in players['fantasy_team'].values:
            continue

        (t1_name, t1_players), (t2_name, t2_players) = players.groupby('fantasy_team')

        matchup = positions.copy()[[]]

        matchup = matchup.join(t1_players.set_index('spos')[['name', 'score']], how='left').rename(columns={'name': t1_name, 'score': team_score(t1_players)})

        matchup = matchup.join(t2_players.set_index('spos')[['score', 'name']], how='left', rsuffix='_2').rename(columns={'name': t2_name, 'score': team_score(t2_players)})

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
