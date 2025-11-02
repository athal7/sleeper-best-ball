import streamlit as st
import pandas as pd
from sleeper_wrapper import League, User, get_sport_state, Stats, Players, League
import requests
from dataclasses import dataclass

TEAM_MAPPINGS = {
    'WSH': 'WAS',
}
POSITION_MAPPINGS = pd.DataFrame([
    ['QB', 'QB', ['QB']],
    ['RB', 'RB', ['RB']],
    ['WR', 'WR', ['WR']],
    ['TE', 'TE', ['TE']],
    ['FLEX', 'FX', ['RB', 'WR', 'TE']],
    ['SUPER_FLEX', 'SFX', ['QB', 'RB', 'WR', 'TE']],
    ['K', 'K', ['K']],
    ['DEF', 'DEF', ['DEF']],
    ['BN', 'BN', ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']],
]).rename(columns={1: 'position', 2: 'eligible'}).set_index(0)


@dataclass
class Data:
    _game_statuses: pd.DataFrame = None
    _matchups: pd.DataFrame = None
    _rosters: pd.DataFrame = None
    _users: pd.DataFrame = None
    _players: pd.DataFrame = None
    _projections: pd.DataFrame = None
    _stats: pd.DataFrame = None
    _scoring: dict = None
    _positions: list[str] = None

    @staticmethod
    def from_league(league: League, season: int, week: int):
        return Data(
            _game_statuses=_game_statuses(season, week),
            _matchups=pd.DataFrame(league.get_matchups(week)),
            _rosters=pd.DataFrame(league.get_rosters()).set_index(
                'roster_id')[['owner_id']],
            _users=pd.DataFrame(league.get_users()).set_index(
                'user_id')[['display_name', 'metadata']],
            _players=pd.DataFrame.from_dict(
                Players().get_all_players("nfl"), orient='index')[['team', 'first_name', 'last_name', 'position']],
            _projections=Stats().get_week_projections("regular", season, week),
            _stats=Stats().get_week_stats("regular", season, week),
            _scoring=league.get_league()['scoring_settings'],
            _positions=league.get_league()['roster_positions']
        )

    def players(self):
        df = self._players.copy()
        df = df[df['team'].notna()]
        df['name'] = df.apply(
            lambda row: f"{row['first_name'][0]}. {row['last_name']}", axis=1)
        df = df.join(self._game_statuses, on='team', how='left')
        df['pct_played'] = (df['status.period'] * 15 -
                            df['status.clock'] / 60) / 60
        df['pct_played'] = df['pct_played'].clip(0, 1)
        df.loc[df['pct_played'].isna(), 'pct_played'] = 0
        df['points'] = df.apply(_points(self._stats, self._scoring), axis=1)
        df['projection'] = df.apply(
            _points(self._projections, self._scoring), axis=1)
        df['optimistic'] = df.apply(
            lambda row: row['points'] + (1 - row['pct_played']) * row['projection'], axis=1)
        return df[['name', 'team', 'position', 'pct_played', 'points', 'projection', 'optimistic']]

    def starting_positions(self):
        df = POSITION_MAPPINGS.copy()
        df = df.join(pd.Series(self._positions).value_counts(), how='inner')
        df = df.loc[df.index.repeat(df['count'])].reset_index(drop=True)
        counts = df.groupby('position').cumcount()
        df['spos'] = df.apply(
            lambda row: f"{row['position']}{counts[row.name]+1}" if counts[row.name] > 0 else row['position'], axis=1)
        df.set_index('spos', inplace=True)
        return df[['position', 'eligible']]

    def matchups(self):
        df = self._matchups
        df = df.join(self._rosters, on='roster_id', how='left')
        df = df.join(self._users.rename(
            columns={'display_name': 'username'}), on='owner_id', how='left')
        df['fantasy_team'] = df.apply(
            lambda row: row['metadata'].get('team_name') or f"Team {row['username']}", axis=1)
        return df[['fantasy_team', 'username', 'points',  'matchup_id', 'players']]


def _leagues(season, params):
    username = params.get('username')
    locked_league_id = params.get('league')
    leagues = []

    if locked_league_id:
        leagues = [locked_league_id]
    elif username:
        user = User(username)
        leagues = [l['league_id'] for l in user.get_all_leagues('nfl', season)]
        if not leagues:
            st.warning("No leagues found for this user.")
    else:
        st.text_input("Enter your Sleeper username:", key='username_input',
                      on_change=lambda: st.query_params.update({'username': st.session_state.username_input}), value=username)
    return leagues


def _game_statuses(season: int, week: int):
    url = f"https://partners.api.espn.com/v2/sports/football/nfl/events?limit=50&season={season}&week={week}"
    resp = requests.get(url)
    data = resp.json()
    df = pd.json_normalize([e['competitions'][0]
                           for e in data['events']])
    df = df.explode('competitors')
    df['team'] = df['competitors'].apply(lambda x: x['team']['abbreviation'])
    df['team'] = df['team'].replace(TEAM_MAPPINGS)
    df.set_index('team', inplace=True)
    return df[['status.period', 'status.clock']]


def _points(stats: dict, scoring: dict):
    def _compute(row):
        total = 0.0
        player_stats = stats.get(row.name, {})
        for stat, pts in scoring.items():
            if stat in player_stats and pd.notnull(player_stats[stat]):
                total += player_stats[stat] * pts
        return total
    return _compute


def _set_starting_positions(team: pd.DataFrame, positions: pd.DataFrame):
    df = team.copy().sort_values(by=['optimistic'], ascending=False)
    df['spos'] = None
    for spos, eligible in positions.iterrows():
        starter = df.loc[(df['position'].isin(eligible['eligible'])) & (
            df['spos'].isnull()), 'spos'].head(1).index
        df.loc[starter, 'spos'] = spos
    df = df[df['spos'].notnull()]
    return df


def _live_team_projection(team: pd.DataFrame):
    starters = team[~team['spos'].str.startswith('BN')]
    projection = f"{starters['optimistic'].sum():.2f}"
    return projection


def _style():
    st.html("""
    <style>
    h1 {
        font-size: 2em !important;
    }
    table {
        width: 100%; 
        max-width: 600px; 
        border-spacing:0; 
        padding:0; 
        text-align: left;
        table-layout: fixed;
    }
    th {
        font-weight: normal;
        padding: 0;
        margin: 0;
    }
    td.username {
        font-size: 0.8em;
        opacity: 0.7;
    }
    td {
        padding: 0;
        margin: 0;
    }
    td.projection {
        font-style: italic;
    }
    table.players td.actual, table.players td.projection {
        font-size: 0.9em;
    }
    td.position, th.position {
        text-align: center;
        vertical-align: middle;
        font-size: 0.6em;
        opacity: 0.7;
    }
    td.player {
        font-size: 0.9em;
    }
    td.player-info {
        font-size: 0.7em;
        opacity: 0.7;
    }
    td.label {
        margin: 0;
        padding: 0;
        font-size: 0.7em;
        font-style: normal;
        opacity: 0.7;
    }
    hr {
        border: none;
        border-top: 1px solid rgba(128, 128, 128, 0.3);
    }

    @media (prefers-color-scheme: dark) {
        hr {
            border-top: 1px solid rgba(255, 255, 255, 0.3);
        }
    }
    @media (prefers-color-scheme: light) {
        td.live {
            background: #fff3b0;
            color: #000;
        }
    }

    @media (prefers-color-scheme: dark) {
        td.live {
            background: #3b2f00;
            color: #fff6d0;
        }
    }
    </style>
    """)


def _is_active(player: dict):
    return player['pct_played'] < 1.0 and player['pct_played'] > 0.0


def _is_final(player: dict):
    return player['pct_played'] == 1


def _player_scores(positions: pd.DataFrame, team1: pd.DataFrame, team2: pd.DataFrame):
    null_player = {'name': '-', 'points': 0.0, 'optimistic': 0.0, 'projection': 0.0,
                   'pct_played': 0.0, 'team': '', 'position': ''}
    rows = []
    for pos, row in positions.iterrows():
        t1 = team1[team1['spos'] == pos]
        t2 = team2[team2['spos'] == pos]
        if t1.empty or t2.empty:
            p1 = null_player
            p2 = null_player
        else:
            p1 = t1.to_dict(orient='records')[0]
            p2 = t2.to_dict(orient='records')[0]

        rows.append(f"""                    
            <tr>
            <td colspan="3" class="player {'live' if _is_active(p1) else ''}">{p1['name']}</td>
            <td rowspan="2" class="position">{row['position']}</td>
            <td colspan="3" class="player {'live' if _is_active(p2) else ''}">{p2['name']}</td>
            </tr>
            <tr>
            <td class="player-info">{p1['position']} {p1['team']}</td>
            <td class="actual">{p1['points']:.2f}</td>
            <td class="projection">{(p1['projection'] if _is_final(p1) else p1['optimistic']):.2f}</td>
            <td class="player-info">{p2['position']} {p2['team']}</td>
            <td class="actual">{p2['points']:.2f}</td>
            <td class="projection">{(p2['projection'] if _is_final(p2) else p2['optimistic']):.2f}</td>
            </tr>
        """)
    st.html(f"""
    <table class="players">
        <tbody>
            {'<tr><td colspan="7"><hr></td></tr>'.join(rows)}
        </tbody>
    </table>
    """)


def _matchup_display(team1, team2, positions, players):
    t1_players = _set_starting_positions(
        players.loc[team1['players']], positions)
    t2_players = _set_starting_positions(
        players.loc[team2['players']], positions)

    st.html(f"""
    <table class="summary">
        <thead>
            <tr>
                <th colspan=2>{team1['fantasy_team']}</th>
                <th></th>
                <th colspan=2>{team2['fantasy_team']}</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td colspan=2 class="username">@{team1['username']}</td>
                <td rowspan=2 class="position">vs</td>
                <td colspan=2 class="username">@{team2['username']}</td>
            </tr>
            <tr>
                <td class="label">score</td>
                <td class="label">projection</td>
                <td class="label">score</td>
                <td class="label">projection</td>
            </tr>
            <tr>
                <td class="actual">{team1['points']:.2f}</td>
                <td class="projection">{_live_team_projection(t1_players)}</td>
                <td></td>
                <td class="actual">{team2['points']:.2f}</td>
                <td class="projection">{_live_team_projection(t2_players)}</td>
            </tr>
        </tbody>
    </table>
    """)
    with st.expander("Show players"):
        _player_scores(
            positions[~positions.index.str.startswith('BN')], t1_players, t2_players)
        with st.expander("Show bench"):
            _player_scores(
                positions[positions.index.str.startswith('BN')], t1_players, t2_players)


def main():
    _style()
    current = get_sport_state('nfl')
    season = int(current['league_season'])
    week = int(current['display_week'])
    username = st.query_params.get('username')
    leagues = _leagues(season, st.query_params)
    if not leagues:
        st.title("Sleeper Best Ball 🏈")
        st.markdown("*optimistic projections for best ball scoring*")

    for league_id in leagues:
        league = League(league_id)
        st.markdown(f"## {league.get_league_name()}: Week {week}")
        data = Data.from_league(league, season, week)
        positions = data.starting_positions()
        players = data.players()
        matchups = data.matchups()
        if username:
            user_matchup = matchups[matchups['username'] == username]
            matchups.drop(user_matchup.index, inplace=True)
            matchups = pd.concat([user_matchup, matchups])
        while not matchups.empty:
            team1 = matchups.iloc[0]
            matchups.drop(team1.name, inplace=True)
            team2 = matchups[matchups['matchup_id']
                             == team1['matchup_id']].iloc[0]
            matchups.drop(team2.name, inplace=True)
            _matchup_display(team1, team2, positions, players)

        st.markdown(f"(League ID: {league_id})")


if __name__ == "__main__":
    main()
