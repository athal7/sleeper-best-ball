import requests
import pandas as pd
from sleeper_wrapper import Stats, Players, League
from dataclasses import dataclass


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
