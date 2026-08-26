import streamlit as st
import numpy as np
import pandas as pd
import requests
from dataclasses import InitVar, dataclass, field
from typing import Optional, List
from yattag import Doc

import sleeper_wrapper as sleeper

METADATA_TTL = 60 * 60  # 1 hour
STATIC_TTL = 60 * 60 * 24  # 24 hours
STATS_TTL = 60 * 5      # 5 minutes
DRAFT_TTL = 60          # 60 seconds - live draft pick polling


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
        if df.empty:
            return df
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

        users = pd.json_normalize(league.get_users())
        if not users.empty and 'user_id' in users.columns:
            users.set_index('user_id', inplace=True)
        else:
            # Create empty DataFrame with properly named index for merge compatibility
            users = pd.DataFrame(columns=['display_name', 'avatar', 'metadata.team_name'])
            users.index.name = 'user_id'
        for col in ['display_name', 'avatar', 'metadata.team_name']:
            if col not in users.columns:
                users[col] = None
        users = users[['display_name', 'avatar', 'metadata.team_name']]

        df = df.merge(users, left_on='owner_id', right_index=True, how='left')
        df.rename(columns={'display_name': 'username'}, inplace=True)
        df['name'] = df['metadata.team_name'].replace(
            '', pd.NA).fillna("Team " + df['username'])
        return df[['avatar', 'username', 'name', 'record', 'rank']]

    @staticmethod
    @st.cache_data(ttl=STATIC_TTL)
    def get_players() -> pd.DataFrame:
        return pd.DataFrame.from_dict(
            sleeper.Players().get_all_players("nfl"), orient='index')

    @staticmethod
    @st.cache_data(ttl=METADATA_TTL)
    def get_projections(season: int, week: int) -> pd.DataFrame:
        return pd.DataFrame(sleeper.Stats().get_week_projections("regular", season, week))

    @staticmethod
    @st.cache_data(ttl=STATIC_TTL)
    def get_bye_weeks(season: int) -> dict[str, int]:
        weekly_teams = {}
        for week in SEASON_WEEKS:
            response = requests.get(
                "https://partners.api.espn.com/v2/sports/football/nfl/events",
                params={'limit': 50, 'season': season, 'week': week},
            )
            response.raise_for_status()
            events = response.json().get('events', [])
            teams = {
                Data.TEAM_MAPPINGS.get(competitor['team']['abbreviation'],
                                       competitor['team']['abbreviation'])
                for event in events
                for competitor in event['competitions'][0]['competitors']
            }
            if teams:
                weekly_teams[week] = teams
        return _derive_bye_weeks(weekly_teams)

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


SLOT_ELIGIBILITY = {slot: eligible for slot, _, eligible in Positions.MAPPINGS}


@dataclass
class DraftSettings:
    teams: int
    slots: dict[str, int]  # e.g. {'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 1, 'SUPER_FLEX': 1}

    SLOT_KEY_MAP = {
        'slots_qb': 'QB', 'slots_rb': 'RB', 'slots_wr': 'WR', 'slots_te': 'TE',
        'slots_flex': 'FLEX', 'slots_super_flex': 'SUPER_FLEX',
        'slots_k': 'K', 'slots_def': 'DEF',
    }

    @classmethod
    def from_draft(cls, draft: dict) -> 'DraftSettings':
        settings = draft['settings']
        slots = {label: settings[key] for key, label in cls.SLOT_KEY_MAP.items()
                  if settings.get(key, 0) > 0}
        return cls(teams=settings['teams'], slots=slots)

    @property
    def relevant_positions(self) -> set[str]:
        return {p for slot in self.slots for p in SLOT_ELIGIBILITY[slot]}


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
        if df.empty or 'roster_id' not in df.columns:
            return []
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


SEASON_WEEKS = range(1, 19)  # NFL regular season: weeks 1-18
Z_90TH_PERCENTILE = 1.2816   # standard-normal z-score for the 90th percentile

# Fallback scoring when a draft has no linked league (e.g. a standalone mock
# draft) and therefore no custom scoring_settings to read - a standard PPR
# baseline using the same stat field names Sleeper's projections use.
DEFAULT_SCORING = {
    'pass_yd': 0.04, 'pass_td': 4, 'pass_int': -2,
    'rush_yd': 0.1, 'rush_td': 6,
    'rec': 1, 'rec_yd': 0.1, 'rec_td': 6,
    'fum_lost': -2,
}


@st.cache_data(ttl=METADATA_TTL)
def fetch_draft_scoring(league_id: Optional[str]) -> dict:
    """Real league scoring (so TE-premium bonuses like bonus_rec_te are honored)
    when the draft is linked to one, else a standard PPR fallback."""
    if league_id and league_id != '0':
        return sleeper.League(league_id).get_league()['scoring_settings']
    return DEFAULT_SCORING


def _derive_bye_weeks(weekly_teams: dict[int, set[str]]) -> dict[str, int]:
    all_teams = set().union(*weekly_teams.values()) if weekly_teams else set()
    return {
        team: missing[0]
        for team in all_teams
        if len(missing := [week for week, teams in weekly_teams.items()
                           if team not in teams]) == 1
    }


@st.cache_data(ttl=METADATA_TTL)
def build_projection_inputs(season: int, scoring: dict) -> tuple[pd.DataFrame, pd.Series]:
    weekly_points = {}
    weekly_adp = {}
    for week in SEASON_WEEKS:
        stats = Data.get_projections(season, week)
        if stats.empty:
            continue
        compute = League._calc_points_from_stats(stats, scoring)
        weekly_points[week] = stats.T.apply(compute, axis=1)
        if 'adp_dd_ppr' in stats.index:
            weekly_adp[week] = pd.to_numeric(
                stats.loc['adp_dd_ppr'], errors='coerce')
    adp = (pd.DataFrame(weekly_adp).bfill(axis=1).iloc[:, 0]
           if weekly_adp else pd.Series(dtype=float))
    return pd.DataFrame(weekly_points), adp


@st.cache_data(ttl=METADATA_TTL)
def build_season_projections(season: int, scoring: dict) -> pd.DataFrame:
    weekly, adp = build_projection_inputs(season, scoring)
    mean_pts = weekly.sum(axis=1, skipna=True)
    p50_weekly = weekly.median(axis=1, skipna=True)
    ceiling_90 = (weekly.mean(axis=1, skipna=True) +
                  Z_90TH_PERCENTILE * weekly.std(axis=1, skipna=True).fillna(0.0))
    return pd.DataFrame({
        'mean_pts': mean_pts,
        'p50_weekly': p50_weekly,
        'ceiling_90': ceiling_90,
        'adp': adp,
    })


@st.cache_data(ttl=DRAFT_TTL)
def get_user_drafts(username: str, season: int) -> tuple[str, list]:
    """Returns (user_id, drafts) for the given Sleeper username and season."""
    user = sleeper.User(username)
    return user.get_user_id(), user.get_all_drafts('nfl', season)


def build_player_pool(projections: pd.DataFrame, settings: DraftSettings, picks: list[dict],
                      bye_weeks: dict[str, int]) -> pd.DataFrame:
    players = Data.get_players()[['position', 'first_name', 'last_name', 'team']]
    pool = projections.join(players, how='inner')
    pool = pool[pool['position'].isin(settings.relevant_positions)]
    drafted_ids = {p['player_id'] for p in picks}
    pool = pool.assign(
        drafted=pool.index.isin(drafted_ids),
        bye_week=pool['team'].map(bye_weeks),
    )
    return pool


def build_my_roster(picks: list[dict], user_id: str, bye_weeks: dict[str, int]) -> pd.DataFrame:
    my_player_ids = [p['player_id'] for p in picks if p.get('picked_by') == user_id]
    roster = Data.get_players()[['position', 'first_name', 'last_name', 'team']].reindex(my_player_ids)
    roster['bye_week'] = roster['team'].map(bye_weeks)
    return roster


class PositionDemand(pd.DataFrame):
    CLIFF_SEARCH_MIN_RANK = 5
    CLIFF_SEARCH_MAX_RANK = 60
    CLIFF_THRESHOLD = 2.0

    def __init__(self, pool: pd.DataFrame, settings: DraftSettings):
        rows = {}
        for pos in settings.relevant_positions:
            own = pool[(pool['position'] == pos) & (pool['mean_pts'] > 0)] \
                .sort_values('mean_pts', ascending=False)
            base_total = self._find_replacement_rank(own['mean_pts'].to_numpy())
            starter_demand = (
                getattr(settings, 'teams', 0)
                * effective_position_needs(settings).get(pos, 0)
            )
            total = max(base_total, starter_demand)
            viable = own.iloc[:total]
            undrafted_viable = viable[~viable['drafted']]
            remaining = len(undrafted_viable)
            replacement_ceiling = (
                undrafted_viable.sort_values('mean_pts')['ceiling_90'].iloc[0]
                if remaining else 0.0
            )
            scarcity = total / remaining if remaining else float('inf')
            rows[pos] = {
                'total_viable': total,
                'remaining_viable': remaining,
                'replacement_ceiling': replacement_ceiling,
                'scarcity_multiplier': scarcity,
                'is_cliff': scarcity > self.CLIFF_THRESHOLD,
            }
        super().__init__(pd.DataFrame.from_dict(rows, orient='index'))

    @classmethod
    def _find_replacement_rank(cls, sorted_desc_values: np.ndarray) -> int:
        n = len(sorted_desc_values)
        hi = min(cls.CLIFF_SEARCH_MAX_RANK, n - 1)
        if n < 2 or hi <= cls.CLIFF_SEARCH_MIN_RANK:
            return n
        drops = (sorted_desc_values[:-1] - sorted_desc_values[1:]) / sorted_desc_values[:-1]
        idx = cls.CLIFF_SEARCH_MIN_RANK + int(np.argmax(drops[cls.CLIFF_SEARCH_MIN_RANK:hi]))
        return idx + 1


def compute_bb_vorp(pool: pd.DataFrame, next_pick_number: int) -> pd.Series:
    undrafted = pool.loc[~pool['drafted']]
    replacement_candidates = undrafted.loc[undrafted['adp'].gt(next_pick_number)]
    replacement = replacement_candidates.loc[
        replacement_candidates.groupby('position')['adp'].idxmin()
    ].set_index('position')['ceiling_90']
    return undrafted['ceiling_90'] - undrafted['position'].map(replacement).fillna(0.0)


def effective_position_needs(settings: DraftSettings) -> dict[str, int]:
    needs = {
        slot: count
        for slot, count in settings.slots.items()
        if slot not in ('FLEX', 'SUPER_FLEX')
    }
    for pos in SLOT_ELIGIBILITY['FLEX']:
        needs[pos] = needs.get(pos, 0) + settings.slots.get('FLEX', 0)
    needs['QB'] = needs.get('QB', 0) + settings.slots.get('SUPER_FLEX', 0)
    return needs


BYE_OVERLAP_DECAY = 0.15  # per already-owned same-position/same-bye player


def compute_personal_score(pool: pd.DataFrame, bb_vorp: pd.Series,
                            my_roster: pd.DataFrame, settings: DraftSettings) -> pd.Series:
    """Adjusts league-wide BB-VORP for the user's own roster construction:

    - Need boost: +1.0x per still-unfilled slot toward effective_position_needs
      (dedicated + FLEX/SUPER_FLEX-driven extras - e.g. in a superflex league,
      still need 2 of 2 effective QB slots -> 3.0x, need 0 more -> 1.0x/no change).
    - Bye-week discount: divides by (1 + BYE_OVERLAP_DECAY * n) where n is how
      many of the user's own players at that position already share that bye
      week - best ball lineups lose depth the week several similar players
      are all out, so stacking is discouraged, never disqualified.

    Positions/players are never penalized below the pure BB-VORP baseline for
    already having "enough" - best ball drafts many bench players beyond the
    minimum starters, and depth still has value. my_roster is the user's full
    roster (see build_my_roster) - independent of the recommendation pool's
    relevant-position/has-projection filtering.
    """
    my_position_counts = my_roster['position'].value_counts()
    need_multiplier = {
        pos: 1.0 + max(0, needed - my_position_counts.get(pos, 0))
        for pos, needed in effective_position_needs(settings).items()
    }
    bye_counts = my_roster.groupby(['position', 'bye_week']).size()

    undrafted = pool[~pool['drafted']]
    need = undrafted['position'].map(need_multiplier).fillna(1.0)
    overlap_keys = pd.MultiIndex.from_arrays([undrafted['position'], undrafted['bye_week']])
    overlap = pd.Series(
        bye_counts.reindex(overlap_keys).fillna(0).to_numpy(), index=undrafted.index)
    bye_discount = 1.0 / (1 + BYE_OVERLAP_DECAY * overlap)

    return bb_vorp.reindex(undrafted.index) * need * bye_discount

def _best_lineup_score(positions: pd.Series, scores: pd.Series,
                       slots: list[str]) -> float:
    states = {0: 0.0}
    position_values = positions.to_numpy()
    score_values = scores.fillna(0.0).to_numpy()
    for slot in slots:
        next_states = {}
        for mask, total in states.items():
            for index, position in enumerate(position_values):
                if mask & (1 << index) or position not in SLOT_ELIGIBILITY[slot]:
                    continue
                candidate = total + score_values[index]
                next_mask = mask | (1 << index)
                next_states[next_mask] = max(next_states.get(next_mask, 0.0), candidate)
        states = next_states
    return max(states.values(), default=0.0)


def compute_weekly_lineup_bonus(pool: pd.DataFrame, weekly_points: pd.DataFrame,
                                my_roster: pd.DataFrame,
                                settings: DraftSettings) -> pd.Series:
    undrafted = pool[~pool['drafted']]
    bonus = pd.Series(0.0, index=undrafted.index)
    slots = [
        slot
        for slot, count in settings.slots.items()
        for _ in range(count)
    ]
    roster_points = weekly_points.reindex(my_roster.index)
    for week in weekly_points.columns:
        scores = roster_points[week] if week in roster_points else pd.Series(dtype=float)
        baseline = _best_lineup_score(my_roster['position'], scores, slots)
        without_slot = [
            _best_lineup_score(
                my_roster['position'], scores, slots[:index] + slots[index + 1:])
            for index in range(len(slots))
        ]
        candidate_scores = weekly_points[week].reindex(undrafted.index).fillna(0.0)
        for position in undrafted['position'].unique():
            eligible_scores = [
                without_slot[index]
                for index, slot in enumerate(slots)
                if position in SLOT_ELIGIBILITY[slot]
            ]
            if eligible_scores:
                candidate_index = undrafted.index[undrafted['position'] == position]
                bonus.loc[candidate_index] += np.maximum(
                    0.0, candidate_scores.loc[candidate_index] +
                    max(eligible_scores) - baseline)
    return bonus / max(len(weekly_points.columns), 1)


def _on_clock_slot(draft: dict, pick_no: int) -> int:
    teams = draft['settings']['teams']
    round_no = (pick_no - 1) // teams + 1
    pos_in_round = (pick_no - 1) % teams + 1
    if draft.get('type') == 'linear':
        return pos_in_round
    return pos_in_round if round_no % 2 == 1 else teams - pos_in_round + 1


def next_user_pick_number(draft: dict, picks_made: int, user_id: str) -> int:
    current_pick = picks_made + 1
    if draft.get('type') == 'auction':
        return current_pick

    user_slot = (draft.get('draft_order') or {}).get(user_id)
    if user_slot is None:
        return current_pick

    teams = draft['settings']['teams']
    for pick_no in range(current_pick, current_pick + 2 * teams):
        if _on_clock_slot(draft, pick_no) == user_slot:
            return pick_no
    return current_pick


def is_users_turn(draft: dict, picks_made: int, user_id: str) -> bool:
    if draft.get('type') == 'auction':
        return True
    user_slot = (draft.get('draft_order') or {}).get(user_id)
    return user_slot == _on_clock_slot(draft, picks_made + 1)


@dataclass
class DraftData:
    draft_id: InitVar[str]
    draft: dict = None
    picks: list = None

    def __post_init__(self, draft_id: str):
        if self.draft is None:
            self.draft = self.get_draft(draft_id)
        if self.picks is None:
            self.picks = self.get_picks(draft_id)

    @staticmethod
    @st.cache_data(ttl=DRAFT_TTL)
    def get_draft(draft_id: str) -> dict:
        return sleeper.Drafts(draft_id).get_specific_draft()

    @staticmethod
    @st.cache_data(ttl=DRAFT_TTL)
    def get_picks(draft_id: str) -> list:
        return sleeper.Drafts(draft_id).get_all_picks()


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
        is_regular_season = current['season_type'] == 'regular'
        display_week = int(current['display_week'])
        self.week = st.session_state.get(
            'week') or (display_week if is_regular_season and display_week > 0 else 1)
        self.leagues = []
        for league_id in self._leagues(self.season, st.query_params.to_dict()):
            data = Data(league_id=league_id, context=self)
            self.leagues.append(League(data=data))


def render_my_roster(my_roster: pd.DataFrame, settings: DraftSettings):
    st.subheader("Your Roster So Far")
    if my_roster.empty:
        st.caption("No picks yet.")
        return
    counts = my_roster['position'].value_counts()
    needs = ", ".join(
        f"{pos} {counts.get(pos, 0)}/{needed}"
        for pos, needed in effective_position_needs(settings).items()
    )
    st.caption(f"Effective starter progress (incl. FLEX/SUPER_FLEX demand): {needs}")
    display = my_roster.copy()
    display['name'] = display['first_name'] + ' ' + display['last_name']
    st.dataframe(
        display[['name', 'position', 'team', 'bye_week']].sort_values('position'),
        hide_index=True,
    )


def _highlight_cliff_row(row: pd.Series) -> list[str]:
    return ['background-color: #ffcccc' if row['Cliff?'] else ''] * len(row)


def render_recommendations(pool: pd.DataFrame, demand: PositionDemand):
    st.subheader("Top 5 Recommendations")
    top5 = pool[~pool['drafted']].sort_values(
        ['personal_score', 'ceiling_90'], ascending=False).head(5).copy()
    top5['name'] = top5['first_name'] + ' ' + top5['last_name']
    top5['Cliff?'] = top5['position'].map(demand['is_cliff']).fillna(False)
    display = top5[['name', 'position', 'team', 'p50_weekly', 'ceiling_90',
                    'bb_vorp', 'weekly_lineup_bonus', 'personal_score', 'Cliff?']]
    styled = (display.style
              .apply(_highlight_cliff_row, axis=1)
              .format({
                  'p50_weekly': '{:.1f}', 'ceiling_90': '{:.1f}', 'bb_vorp': '{:.1f}',
                  'weekly_lineup_bonus': '{:.1f}', 'personal_score': '{:.1f}',
                  'Cliff?': lambda v: '\U0001f525 Cliff' if v else '',
              }))
    st.dataframe(styled, hide_index=True)


@st.fragment(run_every=DRAFT_TTL)
def _draft_assistant_fragment(draft_id: str, user_id: str):
    data = DraftData(draft_id=draft_id)
    settings = DraftSettings.from_draft(data.draft)
    scoring = fetch_draft_scoring(data.draft.get('league_id'))
    season = int(data.draft.get('season') or sleeper.get_sport_state('nfl')['league_season'])
    weekly_points, _ = build_projection_inputs(season, scoring)
    projections = build_season_projections(season, scoring)
    bye_weeks = Data.get_bye_weeks(season)
    pool = build_player_pool(projections, settings, data.picks, bye_weeks)
    demand = PositionDemand(pool, settings)
    next_pick_number = next_user_pick_number(
        data.draft, len(data.picks), user_id)
    users_turn = is_users_turn(data.draft, len(data.picks), user_id)
    pool = pool.assign(
        bb_vorp=compute_bb_vorp(pool, next_pick_number).reindex(pool.index))
    my_roster = build_my_roster(data.picks, user_id, bye_weeks)
    weekly_lineup_bonus = compute_weekly_lineup_bonus(
        pool, weekly_points, my_roster, settings)
    personal_score = compute_personal_score(
        pool, pool['bb_vorp'], my_roster, settings) + weekly_lineup_bonus
    pool = pool.assign(
        weekly_lineup_bonus=weekly_lineup_bonus.reindex(pool.index).fillna(0.0),
        personal_score=personal_score.reindex(pool.index))

    st.caption(f"Pick {len(data.picks) + 1} on the clock · refreshes every {DRAFT_TTL}s")
    st.caption(
        f"VORP compares each player with the first same-position ADP after "
        f"your next pick (Pick {next_pick_number}).")
    if users_turn:
        st.success("It's your turn!")
    else:
        st.caption("Not your turn yet — best available shown below anyway.")
    render_my_roster(my_roster, settings)
    render_recommendations(pool, demand)


def render_draft_assistant(username: str):
    st.title("Draft Recommendation Engine \U0001f3af")
    if not username:
        st.info("Enter your Sleeper username in the sidebar to find your active drafts.")
        return

    season = int(sleeper.get_sport_state('nfl')['league_season'])
    try:
        user_id, drafts = get_user_drafts(username, season)
    except Exception as exc:  # noqa: BLE001 - surface any Sleeper lookup failure
        st.error(
            f"Could not load drafts for Sleeper user '{username}'. "
            f"Check the username, or retry if Sleeper is unavailable. ({exc})")
        return

    active_drafts = [d for d in drafts if d.get('status') in ('drafting', 'pre_draft')]
    if not active_drafts:
        st.info("No active drafts found for this user this season.")
        return

    if len(active_drafts) == 1:
        draft_id = active_drafts[0]['draft_id']
        st.query_params['draft_id'] = draft_id
    else:
        labels = {d['draft_id']: d.get('metadata', {}).get('name') or d['draft_id']
                  for d in active_drafts}
        draft_ids = list(labels)
        remembered = st.query_params.get('draft_id')
        default_index = draft_ids.index(remembered) if remembered in draft_ids else 0
        draft_id = st.sidebar.selectbox(
            "Active draft", options=draft_ids, index=default_index, format_func=lambda k: labels[k],
            key="draft_id_select",
            on_change=lambda: st.query_params.update({'draft_id': st.session_state.draft_id_select}))

    _draft_assistant_fragment(draft_id, user_id)


def main():
    username = st.sidebar.text_input(
        "Sleeper username", key='username_input',
        on_change=lambda: st.query_params.update({'username': st.session_state.username_input}),
        value=st.query_params.get('username'))
    mode_options = ["Live Scores", "Draft Assistant"]
    remembered_mode = st.query_params.get('mode', mode_options[0])
    mode_index = mode_options.index(remembered_mode) if remembered_mode in mode_options else 0
    mode = st.sidebar.radio(
        "View", mode_options, index=mode_index, key="app_mode",
        on_change=lambda: st.query_params.update({'mode': st.session_state.app_mode}))
    if mode == "Draft Assistant":
        render_draft_assistant(username)
        return

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

    if context.leagues:
        st.number_input("Week", min_value=1, max_value=18,
                        key='week', value=context.week)

    for league in context.leagues:
        st.markdown(f"## {league.name}")
        for matchup in league.matchups(context):
            matchup.render()
        st.markdown(f"(League ID: {league.id})")


if __name__ == "__main__":
    main()
