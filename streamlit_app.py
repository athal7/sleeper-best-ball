import streamlit as st
import pandas as pd
import requests
from dataclasses import dataclass, field
from typing import Optional, List

import sleeper_wrapper as sleeper

TTLS = {
    'metadata': 3600,
    'stats': 60,
}
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
    _scoring: dict = field(default_factory=dict)
    _positions: List[str] = field(default_factory=list)

    @staticmethod
    @st.cache_data(ttl=TTLS['stats'])
    def _game_statuses(season: int, week: int) -> pd.DataFrame:
        url = f"https://partners.api.espn.com/v2/sports/football/nfl/events?limit=50&season={season}&week={week}"
        resp = requests.get(url)
        data = resp.json()
        df = pd.json_normalize([e['competitions'][0]
                                for e in data['events']])
        df = df.explode('competitors')
        df['team'] = df['competitors'].apply(
            lambda x: x['team']['abbreviation'])
        df['team'] = df['team'].replace(TEAM_MAPPINGS)
        df.set_index('team', inplace=True)
        df['quarter'] = df['status.period']
        df['clock'] = df['status.clock']
        df['game_status'] = df['status.type.shortDetail']
        return df[['quarter', 'clock', 'game_status']]

    @staticmethod
    @st.cache_data(ttl=TTLS['metadata'])
    def _matchups(league_id: int, week: int) -> pd.DataFrame:
        league_id = sleeper.League(league_id)
        return pd.DataFrame(league_id.get_matchups(week))

    @staticmethod
    @st.cache_data(ttl=TTLS['metadata'])
    def _rosters(league_id: int) -> pd.DataFrame:
        league_id = sleeper.League(league_id)
        return pd.DataFrame(league_id.get_rosters()).set_index('roster_id')

    @staticmethod
    @st.cache_data(ttl=TTLS['metadata'])
    def _users(league_id: int) -> pd.DataFrame:
        league_id = sleeper.League(league_id)
        return pd.DataFrame(league_id.get_users()).set_index('user_id')

    @staticmethod
    @st.cache_data(ttl=TTLS['metadata'])
    def _players() -> pd.DataFrame:
        return pd.DataFrame.from_dict(
            sleeper.Players().get_all_players("nfl"), orient='index')

    @staticmethod
    @st.cache_data(ttl=TTLS['metadata'])
    def _projections(season: int, week: int) -> pd.DataFrame:
        return pd.DataFrame(sleeper.Stats().get_week_projections("regular", season, week))

    @staticmethod
    @st.cache_data(ttl=TTLS['stats'])
    def _stats(season: int, week: int) -> pd.DataFrame:
        return pd.DataFrame(sleeper.Stats().get_week_stats("regular", season, week))

    @classmethod
    def from_league(cls, league: 'sleeper.League', season: int, week: int) -> 'Data':
        return cls(
            _game_statuses=cls._game_statuses(season, week),
            _matchups=cls._matchups(league.league_id, week),
            _rosters=cls._rosters(league.league_id),
            _users=cls._users(league.league_id),
            _players=cls._players(),
            _projections=cls._projections(season, week),
            _stats=cls._stats(season, week),
            _scoring=league.get_league()['scoring_settings'],
            _positions=league.get_league()['roster_positions']
        )

    def players(self) -> pd.DataFrame:
        df = self._players.copy(
        )[['team', 'first_name', 'last_name', 'position', 'injury_status']]
        df = df[df['team'].notna()]
        df['name'] = df.apply(
            lambda row: f"{row['first_name'][0]}. {row['last_name']}", axis=1)
        df = df.join(self._game_statuses, on='team', how='left')
        df['pct_played'] = (df['quarter'] * 15 - df['clock'] / 60) / 60
        df['pct_played'] = df['pct_played'].clip(0, 1)
        df['bye'] = False
        df.loc[df['pct_played'].isna(), 'bye'] = True
        df.loc[df['pct_played'].isna(), 'pct_played'] = 0
        df['points'] = df.apply(_points(self._stats, self._scoring), axis=1)
        df['projection'] = df.apply(
            _points(self._projections, self._scoring), axis=1)
        df['optimistic'] = df.apply(
            lambda row: row['points'] + (1 - row['pct_played']) * row['projection'], axis=1)
        return df[['name', 'team', 'position', 'pct_played', 'points', 'projection', 'optimistic', 'bye', 'injury_status', 'game_status']]

    def starting_positions(self) -> pd.DataFrame:
        df = POSITION_MAPPINGS.copy()
        df = df.join(pd.Series(self._positions).value_counts(), how='inner')
        df = df.loc[df.index.repeat(df['count'])].reset_index(drop=True)
        counts = df.groupby('position').cumcount()
        df['spos'] = df.apply(
            lambda row: f"{row['position']}{counts[row.name]+1}" if counts[row.name] > 0 else row['position'], axis=1)
        df.set_index('spos', inplace=True)
        return df[['position', 'eligible']]

    def matchups(self) -> pd.DataFrame:
        df = self._matchups
        df = df.join(self._rosters[['owner_id']], on='roster_id', how='left')
        users = self._users[['avatar', 'display_name', 'metadata']].rename(
            columns={'display_name': 'username'})
        df = df.join(users, on='owner_id', how='left')
        df['name'] = df.apply(
            lambda row: row['metadata'].get('team_name') or f"Team {row['username']}", axis=1)
        return df[['name', 'username', 'points',  'matchup_id', 'players', 'avatar']]


def _points(stats: dict, scoring: dict):
    def _compute(row):
        total = 0.0
        player_stats = stats.get(row.name, {})
        for stat, pts in scoring.items():
            value = player_stats.get(stat)
            if value is not None and pd.notnull(value):
                total += value * pts
        return total
    return _compute


def _set_starting_positions(team: pd.DataFrame, positions: pd.DataFrame):
    cols = {
        'optimistic': 'spos',
        'points': 'current_position',
    }
    df = team.copy()
    for by, col in cols.items():
        df = df.sort_values(by=[by], ascending=False)
        df[col] = None
        for spos, eligible in positions.iterrows():
            starter = df.loc[(df['position'].isin(eligible['eligible'])) & (
                df[col].isnull()), col].head(1).index
            df.loc[starter, col] = spos
        df = df[df[col].notnull()]
    return df.sort_values(by=['optimistic'], ascending=False)


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
    td.username {
        font-size: 0.8em;
        opacity: 0.7;
        line-height: 1em;
    }
    td.yet-to-play {
        font-size: 0.8em;
        opacity: 0.7;
        line-height: 1.5em;
        font-style: italic;
    }
    td {
        padding: 0;
        margin: 0;
    }
    td.actual {
        font-size: 0.9em;
        text-align: right;
        line-height: 0.9em;
    }
    td.projection {
        opacity: 0.7;
        font-size: 0.8em;
        text-align: right;
        line-height: 0.8em;
    }
    td.position {
        text-align: center;
        vertical-align: middle;
        font-size: 0.6em;
        opacity: 0.7;
    }
    td.player {
        font-size: 0.9em;
        line-height: 0.9em;
    }
    td.player-info {
        font-size: 0.7em;
        opacity: 0.7;
    }
    td.player-status {
        font-size: 0.7em;
        font-style: italic;
        opacity: 0.7;
        line-height: 1em;
    }
    td.label {
        margin: 0;
        padding: 0;
        font-size: 0.7em;
        font-style: normal;
        opacity: 0.7;
    }
    td.live {
        font-weight: bold;
    }
    img.avatar {
        width: 35px;
        height: 35px;
        border-radius: 20px;
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
    </style>
    """)


@dataclass
class Player:
    name: str
    position: str
    team: str
    points: float
    projection: float
    optimistic: float
    pct_played: float
    bye: bool
    spos: str
    current_position: str
    injury_status: Optional[str] = None
    game_status: Optional[str] = None

    @classmethod
    def null_player(cls) -> 'Player':
        return cls(name='-', position='', team='', points=0.0, projection=0.0,
                   optimistic=0.0, pct_played=0.0, bye=False, injury_status='', spos='', current_position='', game_status='')

    @property
    def status(self) -> str:
        if self.bye:
            return "BYE"
        elif self.is_out:
            return "OUT"
        else:
            return self.game_status

    @property
    def is_active(self) -> bool:
        return self.pct_played < 1.0 and self.pct_played > 0.0

    @property
    def is_final(self) -> bool:
        return self.pct_played == 1

    @property
    def is_out(self) -> bool:
        return self.injury_status in ['IR', 'Out'] and self.points == 0 and self.projection == 0

    @property
    def optional_points(self) -> str:
        if self.is_out or self.bye:
            return "-"
        return f"{self.points:.2f}"

    @property
    def optional_projection(self) -> str:
        if self.bye or self.is_out:
            return "-"
        elif self.is_final:
            return f"{self.projection:.2f}"
        else:
            return f"{self.optimistic:.2f}"


@dataclass
class FantasyTeam:
    name: str
    username: str
    avatar: str
    matchup_id: str
    players: list[Player]

    @classmethod
    def from_df(cls, df: pd.Series, players: pd.DataFrame, positions: pd.DataFrame) -> 'FantasyTeam':
        players = players.loc[df['players']]
        players = _set_starting_positions(players, positions)
        players = [Player(**p)
                   for p in players.to_dict(orient='records')]
        return cls(
            name=df['name'],
            username=df['username'],
            avatar=df['avatar'],
            matchup_id=df['matchup_id'],
            players=players
        )

    @property
    def starters(self) -> list[Player]:
        return [p for p in self.players if not p.spos.startswith('BN')]

    @property
    def bench(self) -> list[Player]:
        return [p for p in self.players if p.spos.startswith('BN')]

    @property
    def active_players(self) -> list[Player]:
        return [p for p in self.players if p.projection > 0]

    @property
    def played(self) -> list[Player]:
        return [p for p in self.active_players if p.is_final]

    @property
    def projection(self) -> float:
        return f"{sum(p.optimistic for p in self.starters):.2f}"

    @property
    def points(self) -> float:
        return f"{sum(p.points for p in self.players if not p.current_position.startswith('BN')):.2f}"

    def player(self, position: str) -> Player:
        for p in self.players:
            if p.spos == position:
                return p
        return Player.null_player()


def _player_scores(positions: pd.DataFrame, team1: FantasyTeam, team2: FantasyTeam):
    rows = []
    for pos, row in positions.iterrows():
        p1 = team1.player(pos)
        p2 = team2.player(pos)

        rows.append(f"""                    
            <tr>
            <td colspan=2 class="player {'live' if p1.is_active else ''}">{p1.name}</td>
            <td class="actual">{p1.optional_points}</td>
            <td rowspan=3 class="position">{row['position']}</td>
            <td colspan=2 class="player {'live' if p2.is_active else ''}">{p2.name}</td>
            <td class="actual">{p2.optional_points}</td>
            </tr>
            <tr>
            <td colspan=2 class="player-info">{p1.position} - {p1.team}</td>
            <td class="projection">{p1.optional_projection}</td>
            <td colspan=2 class="player-info">{p2.position} - {p2.team}</td>
            <td class="projection">{p2.optional_projection}</td>
            </tr>
            <tr>
            <td colspan=3 class="player-status">{p1.status}</td>
            <td colspan=3 class="player-status">{p2.status}</td>
            </tr>
        """)
    st.html(f"""
    <table class="players">
        <tbody>
            {'<tr><td colspan="7"><hr></td></tr>'.join(rows)}
        </tbody>
    </table>
    """)


def _matchup_display(team1: FantasyTeam, team2: FantasyTeam, positions: pd.DataFrame):
    st.html(f"""
    <table class="summary">
        <tbody>
            <tr>
                <td colspan=2 rowspan=2><img class="avatar" src="https://sleepercdn.com/avatars/thumbs/{team1.avatar}"></td>
                <td class="actual">{team1.points}</td>
                <td rowspan=5 class="position">vs</td>
                <td colspan=2 rowspan=2><img class="avatar" src="https://sleepercdn.com/avatars/thumbs/{team2.avatar}"></td>
                <td class="actual">{team2.points}</td>
            </tr>
            <tr>
                <td class="projection">{team1.projection}</td>
                <td class="projection">{team2.projection}</td>
            </tr>
            <tr>
                <td colspan=3>{team1.name}</td>
                <td colspan=3>{team2.name}</td>
            </tr>
            <tr>
                <td colspan=3 class="username">@{team1.username}</td>
                <td colspan=3 class="username">@{team2.username}</td>
            </tr>
            <tr>
                <td colspan=3 class="yet-to-play">{len(team1.played)} / {len(team1.active_players)}</td>
                <td colspan=3 class="yet-to-play">{len(team2.played)} / {len(team2.active_players)}</td>
            </tr>
        </tbody>
    </table>
    """)
    with st.expander("Show players"):
        _player_scores(
            positions[~positions.index.str.startswith('BN')], team1, team2)
        with st.expander("Show bench"):
            _player_scores(
                positions[positions.index.str.startswith('BN')], team1, team2)


class Context:
    season: int
    week: int
    username: Optional[str]
    league_ids: List[int]

    @staticmethod
    @st.cache_data(ttl=TTLS['metadata'])
    def _leagues(season: int, params: dict):
        username = params.get('username')
        locked_league_id = params.get('league')
        leagues = []

        if locked_league_id:
            leagues = [locked_league_id]
        elif username:
            user = sleeper.User(username)
            leagues = [l['league_id']
                       for l in user.get_all_leagues('nfl', season)]
            if not leagues:
                st.warning("No leagues found for this user.")
        return leagues

    def __init__(self):
        current = sleeper.get_sport_state('nfl')
        self.username = st.query_params.get('username', [None])
        self.season = int(current['league_season'])
        self.week = st.session_state.get('week') or int(current['display_week'])
        self.league_ids = self._leagues(self.season, st.query_params.to_dict())


def main():
    _style()
    context = Context()
    if not context.league_ids:
        st.title("Sleeper Best Ball 🏈")
        st.markdown("*optimistic projections for best ball scoring*")
        st.text_input("Enter your Sleeper username:", key='username_input',
                      on_change=lambda: st.query_params.update({'username': st.session_state.username_input}), value=context.username)

    for league_id in context.league_ids:
        league = sleeper.League(league_id)
        st.markdown(f"## {league.get_league_name()}")
        st.number_input("Week", min_value=1, max_value=18,
                        key='week', value=context.week)

        data = Data.from_league(league, context.season, context.week)
        positions = data.starting_positions()
        players = data.players()
        matchups = data.matchups()
        if context.username:
            user_matchup = matchups[matchups['username'] == context.username]
            matchups.drop(user_matchup.index, inplace=True)
            matchups = pd.concat([user_matchup, matchups])
        while not matchups.empty:
            t1_df = matchups.iloc[0]
            matchups.drop(t1_df.name, inplace=True)
            team1 = FantasyTeam.from_df(t1_df, players, positions)

            t2_df = matchups[matchups['matchup_id']
                             == team1.matchup_id].iloc[0]
            matchups.drop(t2_df.name, inplace=True)
            team2 = FantasyTeam.from_df(t2_df, players, positions)

            _matchup_display(team1, team2, positions)

        st.markdown(f"(League ID: {league_id})")


if __name__ == "__main__":
    main()
