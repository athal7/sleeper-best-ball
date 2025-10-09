import requests
import pandas as pd
from sleeper_wrapper import Stats, Players



team_mappings = {
    'WSH': 'WAS',
}

def _game_status(season, week):
    url = f"https://partners.api.espn.com/v2/sports/football/nfl/events?limit=50&season={season}&week={week}"
    resp = requests.get(url)
    data = resp.json()
    df = pd.json_normalize([e['competitions'][0]
                           for e in data['events']]).explode('competitors')
    df['team'] = df['competitors'].apply(lambda x: x['team']['abbreviation'])
    df['team'] = df['team'].replace(team_mappings)
    df.set_index('team', inplace=True)
    df['pct_played'] = (df['status.period'] * 15 + df['status.clock']) / 60

    return df[['pct_played']]


def _players():
    return pd.DataFrame.from_dict(
        Players().get_all_players("nfl"), orient='index')[['team', 'first_name', 'last_name', 'position']]

def _projections(season, week):
    return pd.DataFrame.from_dict(
        Stats().get_week_projections("regular", season, week), orient='index')

def _compute_projection(scoring):
    def _compute(row):
        total = 0.0
        for stat, pts in scoring.items():
            if stat in row and pd.notnull(row[stat]):
                total += row[stat] * pts
        return total
    return _compute

def players(season, week, scoring):
    df = _players()
    df = df.join(_game_status(season, week), on='team')
    df = df.join(_projections(season, week), on=df.index)
    df['projection'] = df.apply(_compute_projection(scoring), axis=1)
    return df[['first_name', 'last_name', 'team', 'position', 'projection', 'pct_played']]
    
