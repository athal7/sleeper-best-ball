import streamlit as st
import pandas as pd
import requests
from dataclasses import InitVar, dataclass, field
from typing import Optional, List
from yattag import Doc

import sleeper_wrapper as sleeper

METADATA_TTL = 60 * 60  # 1 hour
STATS_TTL = 60 * 5      # 5 minutes


class Style():
    def __init__(self, styles: dict):
        self.styles = styles

    def __getattribute__(self, name):
        try:
            return super().__getattribute__(name)
        except AttributeError:
            return self.get(name)

    def get(self, label: str, **extra) -> str:
        styles = self.styles.get(label, {}).copy()
        if extra:
            styles.update(extra)
        return '; '.join(f'{k.replace("_", "-")}: {v}' for k, v in styles.items()) + ';'


@dataclass
class Data:
    league_id: InitVar[int]
    context: InitVar['Context']
    game_statuses: pd.DataFrame = None
    matchups: pd.DataFrame = None
    rosters: pd.DataFrame = None
    players: pd.DataFrame = None
    projections: pd.DataFrame = None
    stats: pd.DataFrame = None
    league: sleeper.League = None

    TEAM_MAPPINGS = {
        'WSH': 'WAS',
    }

    def __post_init__(self, league_id: int, context: 'Context') -> 'Data':
        if self.game_statuses is None:
            self.game_statuses = self.get_game_statuses(
                context.season, context.week)
        if self.matchups is None:
            self.matchups = self.get_matchups(league_id, context.week)
        if self.rosters is None:
            self.rosters = self.get_rosters(league_id)
        if self.players is None:
            self.players = self.get_players()
        if self.projections is None:
            self.projections = self.get_projections(
                context.season, context.week)
        if self.stats is None:
            self.stats = self.get_stats(context.season, context.week)
        if self.league is None:
            self.league = self.get_league(league_id)

    @staticmethod
    @st.cache_data(ttl=METADATA_TTL)
    def get_league(league_id: int) -> sleeper.League:
        return sleeper.League(league_id)

    @property
    def scoring(self) -> dict:
        return self.league.get_league()['scoring_settings']

    @property
    def positions(self) -> list[str]:
        return self.league.get_league()['roster_positions']

    @staticmethod
    @st.cache_data(ttl=STATS_TTL)
    def get_game_statuses(season: int, week: int) -> pd.DataFrame:
        url = f"https://partners.api.espn.com/v2/sports/football/nfl/events?limit=50&season={season}&week={week}"
        resp = requests.get(url)
        data = resp.json()
        competitions = [e['competitions'][0] for e in data['events']]
        df = pd.json_normalize(competitions)
        df = df.explode('competitors')
        df = df[['id', 'competitors', 'status.period',
                 'status.clock', 'status.type.shortDetail', 'time.value']]
        df = pd.json_normalize(df.to_dict(orient='records'))
        df.rename(columns={
            'competitors.team.abbreviation': 'team',
            'competitors.score.displayValue': 'score',
            'status.type.shortDetail': 'game_status',
            'status.period': 'quarter',
            'status.clock': 'clock',
            'time.value': 'game_time',
            'id': 'game_id'
        }, inplace=True)
        df['home'] = df['competitors.homeAway'] == 'home'
        df['team'] = df['team'].replace(Data.TEAM_MAPPINGS)
        df = df[['team', 'score', 'quarter', 'clock',
                 'game_status', 'home', 'game_id', 'game_time']]
        df = df.merge(df, on='game_id', suffixes=(
            '', '_opponent')).query('team != team_opponent')
        df.set_index('team', inplace=True)
        df.rename(columns={'team_opponent': 'opponent',
                  'score_opponent': 'opponent_score'}, inplace=True)
        return df[['quarter', 'clock', 'game_status', 'home', 'opponent', 'score', 'opponent_score', 'game_time']]

    @staticmethod
    @st.cache_data(ttl=METADATA_TTL)
    def get_matchups(league_id: int, week: int) -> pd.DataFrame:
        league = sleeper.League(league_id)
        last_regular_week = league.get_league()['settings']['playoff_week_start'] - 1
        df = pd.DataFrame(league.get_matchups(week))
        if week > last_regular_week:
            df = df.drop(columns=['matchup_id'])
            
            round = week - last_regular_week
            matchups = []
            matchup_id = 1
            for r in league.get_playoff_winners_bracket():
                if r['r'] == week - last_regular_week:
                    matchups.append({'matchup_id': matchup_id, 'roster_id': r['t1']})
                    matchups.append({'matchup_id': matchup_id, 'roster_id': r['t2']})
                    matchup_id += 1
            for r in league.get_playoff_losers_bracket():
                if r['r'] == week - last_regular_week:
                    matchups.append({'matchup_id': matchup_id, 'roster_id': r['t1']})
                    matchups.append({'matchup_id': matchup_id, 'roster_id': r['t2']})
                    matchup_id += 1
            
            playoff_df = pd.DataFrame(matchups).set_index('roster_id')
            df = df.join(playoff_df, on='roster_id', how='inner').reset_index()
        return df

    @staticmethod
    @st.cache_data(ttl=METADATA_TTL)
    def get_rosters(league_id: int) -> pd.DataFrame:
        league = sleeper.League(league_id)
        df = pd.json_normalize(league.get_rosters()).set_index('roster_id')
        df['record'] = df['settings.wins'].astype(
            str) + '-' + df['settings.losses'].astype(str)
        df.sort_values(by=['settings.wins', 'settings.fpts'],
                       ascending=[False, False], inplace=True)
        df['rank'] = range(1, len(df) + 1)
        df = df[['owner_id', 'players', 'record', 'rank']]

        users = pd.json_normalize(league.get_users()).set_index('user_id')
        users = users[['display_name', 'avatar', 'metadata.team_name']]

        df = df.merge(users, left_on='owner_id', right_index=True, how='left')
        df.rename(columns={'display_name': 'username'}, inplace=True)
        df['name'] = df['metadata.team_name'].replace(
            '', pd.NA).fillna("Team " + df['username'])
        return df[['avatar', 'username', 'name', 'record', 'rank']]

    @staticmethod
    @st.cache_data(ttl=METADATA_TTL)
    def get_players() -> pd.DataFrame:
        return pd.DataFrame.from_dict(
            sleeper.Players().get_all_players("nfl"), orient='index')

    @staticmethod
    @st.cache_data(ttl=METADATA_TTL)
    def get_projections(season: int, week: int) -> pd.DataFrame:
        return pd.DataFrame(sleeper.Stats().get_week_projections("regular", season, week))

    @staticmethod
    @st.cache_data(ttl=STATS_TTL)
    def get_stats(season: int, week: int) -> pd.DataFrame:
        return pd.DataFrame(sleeper.Stats().get_week_stats("regular", season, week))


class Positions(pd.DataFrame):
    MAPPINGS = [
        ['QB', 'QB', ['QB']],
        ['RB', 'RB', ['RB']],
        ['WR', 'WR', ['WR']],
        ['TE', 'TE', ['TE']],
        ['FLEX', 'FX', ['RB', 'WR', 'TE']],
        ['SUPER_FLEX', 'SFX', ['QB', 'RB', 'WR', 'TE']],
        ['K', 'K', ['K']],
        ['DEF', 'DEF', ['DEF']],
        ['BN', 'BN', ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']],
    ]

    def __init__(self, data: Data):
        df = pd.DataFrame(self.MAPPINGS).rename(
            columns={1: 'position', 2: 'eligible'}).set_index(0)
        df = df.join(
            pd.Series(data.positions).value_counts(), how='inner')
        df = df.loc[df.index.repeat(df['count'])].reset_index(drop=True)
        counts = df.groupby('position').cumcount()
        df['spos'] = df['position'] + (counts + 1).astype(str)
        df.set_index('spos', inplace=True)
        super().__init__(df[['position', 'eligible']])


@dataclass
class Player:
    first_name: str = field(default_factory=str)
    last_name: str = field(default_factory=str)
    position: str = field(default_factory=str)
    team: str = field(default_factory=str)
    points: float = field(default_factory=float)
    projection: float = field(default_factory=float)
    optimistic: float = field(default_factory=float)
    pct_played: float = field(default_factory=float)
    bye: bool = field(default_factory=bool)
    spos: str = field(default_factory=str)
    current_position: str = field(default_factory=str)
    injury_status: str = field(default_factory=str)
    game_status: Optional[str] = field(default=None)
    home: Optional[bool] = field(default=None)
    opponent: Optional[str] = field(default=None)
    game_time: Optional[str] = field(default=None)
    score: Optional[int] = field(default=None)
    opponent_score: Optional[int] = field(default=None)

    @property
    def name(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}. {self.last_name}"
        return "N/A"

    def get_status(self) -> str:
        vs = "vs" if self.home else "@"
        if self.bye:
            return "Bye"
        elif self.pct_played == 0 and self.game_time:
            game_time = pd.to_datetime(self.game_time).tz_convert(
                st.context.timezone).strftime('%a %-I:%M %p')
            return f"{game_time} {vs} {self.opponent}"
        else:
            return f"{self.game_status} {self.score}-{self.opponent_score} {vs} {self.opponent}"

    @property
    def is_live(self) -> bool:
        return self.pct_played < 1.0 and self.pct_played > 0.0

    @property
    def is_final(self) -> bool:
        return self.pct_played == 1

    def get_points(self) -> str:
        return "-" if self.points == 0 else f"{self.points:.2f}"

    def get_projection(self) -> str:
        if self.projection == 0:
            return "-"
        elif self.is_final:
            return f"{self.projection:.2f}"
        else:
            return f"{self.optimistic:.2f}"

    INJURY_STATUS_MAP = {
        'Probable': 'P',
        'Questionable': 'Q',
        'Doubtful': 'D',
        'Out': 'O',
        'IR': 'IR',
    }

    @property
    def player_info(self) -> str:
        info = f"{self.position} - {self.team}"
        if self.injury_status:
            info += f" ({self.INJURY_STATUS_MAP.get(self.injury_status, self.injury_status)})"
        return info


class Roster(pd.DataFrame):
    def __init__(self, players: pd.DataFrame, positions: pd.DataFrame):
        df = players.copy()
        cols = {
            'optimistic': 'spos',
            'points': 'current_position',
        }
        for by, col in cols.items():
            df = df.sort_values(by=[by], ascending=False)
            df[col] = None
            for spos, eligible in positions.iterrows():
                starter = df.loc[(df['position'].isin(eligible['eligible'])) & (
                    df[col].isnull()), col].head(1).index
                df.loc[starter, col] = spos
            df = df[df[col].notnull()]
        df = df.sort_values(by=['optimistic'], ascending=False)
        super().__init__(df)

    def to_records(self) -> list[Player]:
        return [Player(**row._asdict()) for row in self.itertuples()]

    @property
    def current_starters(self) -> 'Roster':
        return self[~self['current_position'].str.startswith('BN')]

    @property
    def current_bench(self) -> 'Roster':
        return self[self['current_position'].str.startswith('BN')]

    @property
    def projected_starters(self) -> 'Roster':
        return self[~self['spos'].str.startswith('BN')]

    @property
    def projected_bench(self) -> 'Roster':
        return self[self['spos'].str.startswith('BN')]

    @property
    def active(self) -> 'Roster':
        return self[self['projection'] > 0]

    @property
    def in_progress(self) -> 'Roster':
        return self.active.loc[(self['pct_played'] > 0) & (self['pct_played'] < 1)]

    @property
    def left_to_play(self) -> 'Roster':
        return self.active.loc[self['pct_played'] == 0]

    @property
    def played(self) -> 'Roster':
        return self.active.loc[self['pct_played'] == 1]

    def at_position(self, position: str) -> Player:
        df = self.loc[(self['spos'] == position)]
        if not df.empty:
            return Player(**df.iloc[0].to_dict())
        return Player()


@dataclass
class FantasyTeam:
    players: InitVar[pd.Series]
    all_players: InitVar[pd.DataFrame]
    positions: InitVar[Positions]
    name: str
    username: str
    avatar: str
    matchup_id: str
    record: str
    rank: int
    roster: Roster = field(init=False)

    def __post_init__(self, players: pd.Series, all_players: pd.DataFrame, positions: Positions):
        self.roster = Roster(all_players.loc[players], positions)

    @property
    def avatar_url(self) -> str:
        return f"https://sleepercdn.com/avatars/thumbs/{self.avatar}"

    @property
    def points(self) -> str:
        return f"{self.roster.current_starters.points.sum():.2f}"

    @property
    def projection(self) -> str:
        return f"{self.roster.projected_starters.optimistic.sum():.2f}"

    @property
    def team_info(self) -> str:
        return f"@{self.username} · #{self.rank} ({self.record})"

    @property
    def played_counts(self) -> str:
        return f"{self.roster.played.shape[0]} done / {self.roster.in_progress.shape[0]} live / {self.roster.left_to_play.shape[0]} left"


@dataclass
class Matchup:
    team1: FantasyTeam
    team2: FantasyTeam
    positions: Positions

    def render(self):
        t1 = self.team1
        t2 = self.team2
        doc, tag, text, line = Doc().ttl()
        s = Style({
            'table': {'width': '100%', 'max-width': '600px', 'table-layout': 'fixed'},
            'avatar': {'width': '35px', 'height': '35px', 'border-radius': '20px'},
            'name': {'line-height': '1.2em', 'text-overflow': 'ellipsis', 'overflow': 'hidden', 'white-space': 'nowrap'},
            'live': {'font-weight': 'bold'},
            'info': {'font-size': '0.8em', 'line-height': '0.8em', 'opacity': '0.8'},
            'points': {'line-height': '1.2em', 'text-align': 'right'},
            'projection': {'font-size': '0.8em', 'text-align': 'right', 'line-height': '0.8em', 'opacity': '0.8'},
            'label': {'text-align': 'center', 'vertical-align': 'middle', 'font-size': '0.6em', 'opacity': '0.8'},
            'status': {'font-size': '0.8em', 'font-style': 'italic', 'line-height': '1em', 'opacity': '0.6'},
            'hr': {'border': 'none', 'border-top': '1px solid rgba(128, 128, 128, 0.3)'},
        })
        with tag('table', style=s.table):
            with tag('tbody'):
                with tag('tr'):
                    with tag('td', colspan=2, rowspan=2):
                        doc.stag('img', src=t1.avatar_url, style=s.avatar)
                    line('td', t1.points, style=s.points)
                    line('td', "vs", rowspan="5", style=s.label)
                    with tag('td', colspan=2, rowspan=2):
                        doc.stag('img', src=t2.avatar_url, style=s.avatar)
                    line('td', t2.points, style=s.points)
                with tag('tr'):
                    line('td', t1.projection, style=s.projection)
                    line('td', t2.projection, style=s.projection)
                with tag('tr'):
                    line('td', t1.name, colspan=3, style=s.name)
                    line('td', t2.name, colspan=3, style=s.name)
                with tag('tr'):
                    line('td', t1.team_info, colspan=3, style=s.info)
                    line('td', t2.team_info, colspan=3, style=s.info)
                with tag('tr'):
                    line('td', t1.played_counts, colspan=3, style=s.status)
                    line('td', t2.played_counts, colspan=3, style=s.status)

        st.html(doc.getvalue())
        with st.expander("Show players"):
            self.render_players(self.positions, s)

    def render_players(self, positions: pd.DataFrame, s: Style):
        doc, tag, text, line = Doc().ttl()
        with tag('table', style=s.get('table', font_size="0.9em")):
            with tag('tbody'):
                for idx, (pos, row) in enumerate(positions.iterrows()):
                    if idx > 0:
                        with tag('tr'):
                            with tag('td', colspan=7):
                                doc.stag(
                                    'hr',
                                    style=f"{s.hr} {'border-width:10px' if pos == 'BN1' else ''}"
                                )
                    p1 = self.team1.roster.at_position(pos)
                    p2 = self.team2.roster.at_position(pos)
                    with tag('tr'):
                        line(
                            'td',
                            p1.name,
                            style=f"{s.name} {s.live if p1.is_live else ''}",
                            colspan=2
                        )
                        line('td', p1.get_points(), style=s.points)
                        line('td', row['position'], rowspan=3, style=s.label)
                        line(
                            'td',
                            p2.name,
                            style=f"{s.name} {s.live if p2.is_live else ''}",
                            colspan=2
                        )
                        line('td', p2.get_points(), style=s.points)
                    with tag('tr'):
                        line('td', p1.player_info, colspan=2, style=s.info)
                        line('td', p1.get_projection(), style=s.projection)
                        line('td', p2.player_info, colspan=2, style=s.info)
                        line('td', p2.get_projection(), style=s.projection)
                    with tag('tr'):
                        line('td', p1.get_status(), colspan=3, style=s.status)
                        line('td', p2.get_status(), colspan=3, style=s.status)

        st.html(doc.getvalue())

    def contains_user(self, username: str) -> bool:
        return self.team1.username == username or self.team2.username == username


@dataclass
class League:
    data: Data

    @staticmethod
    def _calc_points_from_stats(stats: dict, scoring: dict):
        def _compute(row):
            total = 0.0
            player_stats = stats.get(row.name, {})
            for stat, pts in scoring.items():
                value = player_stats.get(stat)
                if value is not None and pd.notnull(value):
                    total += value * pts
            return total
        return _compute

    @property
    def id(self) -> int:
        return self.data.league.league_id

    @property
    def name(self) -> str:
        return self.data.league.get_league_name()
    
    @property
    def playoff_week_start(self) -> int:
        return self.data.league.get_league()['settings']['playoff_week_start']

    def players(self) -> pd.DataFrame:
        df = self.data.players.copy(
        )[['team', 'first_name', 'last_name', 'position', 'injury_status']]
        df = df[df['team'].notna()]
        df = df.join(self.data.game_statuses, on='team', how='left')
        df['pct_played'] = (df['quarter'] * 15 - df['clock'] / 60) / 60
        df['pct_played'] = df['pct_played'].clip(0, 1)
        df['bye'] = False
        df.loc[df['pct_played'].isna(), 'bye'] = True
        df.loc[df['pct_played'].isna(), 'pct_played'] = 0
        df['points'] = df.apply(
            self._calc_points_from_stats(self.data.stats, self.data.scoring), axis=1)
        df['projection'] = df.apply(
            self._calc_points_from_stats(self.data.projections, self.data.scoring), axis=1)
        df['optimistic'] = df['points'] + \
            (1 - df['pct_played']) * df['projection']
        return df[['first_name', 'last_name', 'team', 'position', 'pct_played', 'points', 'projection', 'optimistic', 'bye', 'injury_status', 'game_status', 'home', 'opponent', 'score', 'opponent_score', 'game_time']]

    def matchups(self, context) -> list[Matchup]:
        df = self.data.matchups
        df = df.join(self.data.rosters, on='roster_id', how='left')

        all_players = self.players()
        positions = Positions(self.data)
        grouped = []
        # Group by matchup_id and collect teams
        for _, group in df.groupby('matchup_id'):
            teams_df = group[['name', 'username',
                              'matchup_id', 'players', 'avatar', 'record', 'rank']]
            if len(teams_df) == 2:
                team1 = FantasyTeam(
                    **teams_df.iloc[0].to_dict(), all_players=all_players, positions=positions)
                team2 = FantasyTeam(
                    **teams_df.iloc[1].to_dict(), all_players=all_players, positions=positions)
                grouped.append(
                    Matchup(team1=team1, team2=team2, positions=positions))
        # Sort so that matchups involving the context user come first
        if context.username:
            grouped = sorted(
                grouped, key=lambda m: not m.contains_user(context.username))
        return grouped


class Context:
    season: int
    week: int
    username: Optional[str]
    leagues: List[League]

    @staticmethod
    @st.cache_data(ttl=METADATA_TTL)
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
        self.username = st.query_params.get('username')
        self.season = int(current['league_season'])
        self.week = st.session_state.get(
            'week') or int(current['display_week'])
        self.leagues = []
        for league_id in self._leagues(self.season, st.query_params.to_dict()):
            data = Data(league_id=league_id, context=self)
            self.leagues.append(League(data=data))


def main():
    context = Context()
    if not context.leagues:
        st.html("""<style>
            html, body { background-color: #ffffff; }
            @media (prefers-color-scheme: dark) {
                html, body { background-color: #000000 !important; }
                body {
                    margin-top: env(safe-area-inset-top);
                    margin-bottom: env(safe-area-inset-bottom);
                }
            }
            h1 { font-size: 2rem !important; }
        </style>""")
        st.title("Sleeper Best Ball 🏈")
        st.markdown("*optimistic projections for best ball scoring*")
        st.text_input("Enter your Sleeper username:", key='username_input',
                      on_change=lambda: st.query_params.update({'username': st.session_state.username_input}), value=context.username)

    for league in context.leagues:
        st.markdown(f"## {league.name}")
        st.number_input("Week", min_value=1, max_value=18,
                        key='week', value=context.week)
        for matchup in league.matchups(context):
            matchup.render()
        st.markdown(f"(League ID: {league.id})")


if __name__ == "__main__":
    main()
