import requests
import pandas as pd
from sleeper_wrapper import Stats, Players, League


team_mappings = {
    'WSH': 'WAS',
}
positions = pd.DataFrame([
    ['QB', 'QB', ['QB']],
    ['RB', 'RB', ['RB']],
    ['WR', 'WR', ['WR']],
    ['TE', 'TE', ['TE']],
    ['FLEX', 'FLEX', ['RB', 'WR', 'TE']],
    ['SUPER_FLEX', 'SFLEX', ['QB', 'RB', 'WR', 'TE']],
    ['K', 'K', ['K']],
    ['DEF', 'DEF', ['DEF']]
]).rename(columns={1: 'position', 2: 'eligible'}).set_index(0)

def _game_status(season: int, week: int):
    url = f"https://partners.api.espn.com/v2/sports/football/nfl/events?limit=50&season={season}&week={week}"
    resp = requests.get(url)
    data = resp.json()
    df = pd.json_normalize([e['competitions'][0]
                           for e in data['events']]).explode('competitors')
    df['team'] = df['competitors'].apply(lambda x: x['team']['abbreviation'])
    df['team'] = df['team'].replace(team_mappings)
    df.set_index('team', inplace=True)
    df['pct_played'] = (df['status.period'] * 15 * 60 + df['status.clock']) / (60 * 60)

    return df[['pct_played']]


def _players():
    return pd.DataFrame.from_dict(
        Players().get_all_players("nfl"), orient='index')[['team', 'first_name', 'last_name', 'position']]


def _projections(season: int, week: int):
    return pd.DataFrame.from_dict(
        Stats().get_week_projections("regular", season, week), orient='index')


def _projection(league: League):
    scoring = league.get_league()['scoring_settings']

    def _compute(row):
        total = 0.0
        for stat, pts in scoring.items():
            if stat in row and pd.notnull(row[stat]):
                total += row[stat] * pts
        return total
    return _compute


def _matchups(league: League, week: int):
    return pd.DataFrame(league.get_matchups(week))


def _users(league: League):
    return pd.DataFrame(league.get_users()).set_index('user_id')[[
        'display_name']].rename(columns={'display_name': 'fantasy_team'})


def _rosters(league: League):
    return pd.DataFrame(league.get_rosters()).set_index('roster_id')[['owner_id']]


def _optimistic_score(row):
    if pd.isna(row['pct_played']):
        return 0
    elif row['pct_played'] == 0:
        return row['projection']
    elif row['pct_played'] >= 1:
        return row['points']
    else:
        return row['points'] + (1 - row['pct_played']) * row['projection']


def rosters(season: int, week: int, league: League):
    df = _matchups(league, week)
    df = df.explode('players').rename(
        columns={'players': 'player_id'}).set_index('player_id')
    df['points'] = df.apply(
        lambda row: row['players_points'].get(row.name, None), axis=1)
    df = df[['points', 'roster_id', 'matchup_id']]
    df = df.join(_rosters(league), on='roster_id', how='left')
    df = df.join(_users(league), on='owner_id', how='left')
    df = df.join(_players(), how='left')
    df = df.join(_game_status(season, week), on='team', how='left')
    df = df.join(_projections(season, week), on=df.index, how='left')

    df['projection'] = df.apply(_projection(league), axis=1)
    df['points'] = df.apply(_optimistic_score, axis=1)
    df['projected'] = df['pct_played'].apply(
        lambda x: x < 1 if pd.notnull(x) else False)

    return df.sort_values('points', ascending=False)[['first_name', 'last_name', 'team', 'position', 'points', 'fantasy_team', 'matchup_id', 'projected']]


def _position_counts(league: League):
    return pd.Series(league.get_league()['roster_positions']).value_counts()


def starting_positions(league: League):
    df = positions.copy()
    df = df.join(_position_counts(league), how='inner')
    df = df.loc[df.index.repeat(df['count'])].reset_index(drop=True)
    df['position'] = df['position'] + (df.groupby('position').cumcount() + 1).astype(str)
    df.set_index('position', inplace=True)
    return df[['eligible']]