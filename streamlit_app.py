import streamlit as st
import numpy as np
import pandas as pd
import requests
from dataclasses import InitVar, dataclass, field
from typing import Optional, List
from yattag import Doc

import sleeper_wrapper as sleeper

METADATA_TTL = 60 * 60  # 1 hour
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


def _infer_bye_week(weekly_row: pd.Series) -> Optional[int]:
    """A player missing from exactly one week's projections is on bye that
    week; missing from zero or several weeks is ambiguous (e.g. new addition
    mid-season, or a still-incomplete slate) so is left unknown."""
    missing = weekly_row[weekly_row.isna()].index.tolist()
    return missing[0] if len(missing) == 1 else None


@st.cache_data(ttl=METADATA_TTL)
def build_season_projections(season: int, scoring: dict) -> pd.DataFrame:
    """Builds season-long mean/ceiling projections entirely from Sleeper's own
    weekly projections (no external data needed): mean_pts is the projected
    season total, ceiling_90 is the 90th-percentile week from that player's
    own week-to-week projected spread (spike-week potential), bye_week is
    inferred from the one week they're absent from the projections. All
    computed under the given scoring so TE-premium bonuses are reflected.
    Weeks a player has no projection (e.g. bye) are excluded from mean/ceiling,
    not treated as a zero.
    """
    weekly_points = {}
    for week in SEASON_WEEKS:
        stats = Data.get_projections(season, week)
        if stats.empty:
            continue
        compute = League._calc_points_from_stats(stats, scoring)
        # Transpose so .apply(axis=1) iterates real per-player rows (row.name =
        # player_id) - applying to a zero-column frame leaves row.name unset.
        weekly_points[week] = stats.T.apply(compute, axis=1)
    weekly = pd.DataFrame(weekly_points)
    mean_pts = weekly.sum(axis=1, skipna=True)
    ceiling_90 = (weekly.mean(axis=1, skipna=True) +
                  Z_90TH_PERCENTILE * weekly.std(axis=1, skipna=True).fillna(0.0))
    bye_week = weekly.apply(_infer_bye_week, axis=1)
    return pd.DataFrame({'mean_pts': mean_pts, 'ceiling_90': ceiling_90, 'bye_week': bye_week})


@st.cache_data(ttl=METADATA_TTL)
def get_user_drafts(username: str, season: int) -> tuple[str, list]:
    """Returns (user_id, drafts) for the given Sleeper username and season."""
    user = sleeper.User(username)
    return user.get_user_id(), user.get_all_drafts('nfl', season)


def build_player_pool(projections: pd.DataFrame, settings: DraftSettings, picks: list[dict]) -> pd.DataFrame:
    """Merges auto-fetched season projections with Sleeper player metadata (name/team/position,
    reusing Data.get_players()), restricts to positions this draft actually starts
    (settings.relevant_positions), and flags drafted players from the live picks feed.
    """
    players = Data.get_players()[['position', 'first_name', 'last_name', 'team']]
    pool = projections.join(players, how='inner')
    pool = pool[pool['position'].isin(settings.relevant_positions)]
    drafted_ids = {p['player_id'] for p in picks}
    pool = pool.assign(drafted=pool.index.isin(drafted_ids))
    return pool


def build_my_roster(picks: list[dict], user_id: str, projections: pd.DataFrame) -> pd.DataFrame:
    """All of the user's own picks, independent of build_player_pool's
    relevant-position/has-projection filtering - a K/DEF pick, or one for a
    player missing a Sleeper projection row, must still count toward roster
    construction and appear in "Your Roster So Far".
    """
    my_player_ids = [p['player_id'] for p in picks if p.get('picked_by') == user_id]
    roster = Data.get_players()[['position', 'first_name', 'last_name', 'team']].reindex(my_player_ids)
    roster['bye_week'] = projections['bye_week'].reindex(my_player_ids)
    return roster


class PositionDemand(pd.DataFrame):
    CLIFF_SEARCH_MIN_RANK = 5     # ignore the very top studs - too small a group to call a "cliff"
    CLIFF_SEARCH_MAX_RANK = 60    # cap search depth - irrelevant this deep regardless of format
    FLEX_BONUS_PER_SLOT = 0.15    # each shared FLEX/SUPER_FLEX slot type this position is
                                    # eligible for extends its viable tier a bit - it has extra
                                    # paths to relevance beyond its own dedicated need
    CLIFF_THRESHOLD = 2.0

    def __init__(self, pool: pd.DataFrame, settings: DraftSettings):
        rows = {}
        for pos in settings.relevant_positions:
            # Exclude true non-contributors (never expected to see the field) - without
            # this, the long tail of zero-production players swamps any distribution
            # statistic computed over "everyone at this position".
            own = pool[(pool['position'] == pos) & (pool['mean_pts'] > 0)] \
                .sort_values('mean_pts', ascending=False)
            base_total = self._find_replacement_rank(own['mean_pts'].to_numpy())
            shared_slots = sum(
                1 for slot in ('FLEX', 'SUPER_FLEX')
                if slot in settings.slots and pos in SLOT_ELIGIBILITY[slot]
            )
            total = round(base_total * (1 + self.FLEX_BONUS_PER_SLOT * shared_slots))
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
        """Where this position's own projected-value curve drops off hardest,
        in relative (percentage) terms - scale-invariant, so it works whether
        the position's raw point totals run high (QB) or low (TE). Purely a
        function of this position's own values; no roster-slot or team-count
        input at all.
        """
        n = len(sorted_desc_values)
        hi = min(cls.CLIFF_SEARCH_MAX_RANK, n - 1)
        if n < 2 or hi <= cls.CLIFF_SEARCH_MIN_RANK:
            return n
        drops = (sorted_desc_values[:-1] - sorted_desc_values[1:]) / sorted_desc_values[:-1]
        idx = cls.CLIFF_SEARCH_MIN_RANK + int(np.argmax(drops[cls.CLIFF_SEARCH_MIN_RANK:hi]))
        return idx + 1


def compute_bb_vorp(pool: pd.DataFrame, demand: PositionDemand) -> pd.Series:
    """BB-VORP = player's own ceiling_90 minus their position's replacement_ceiling.
    Scarcity is already implicit here - a thin position's population-derived
    replacement level sits low relative to its few remaining good players, which
    widens this gap on its own. No separate scarcity multiplier is applied on top;
    doing so would double-count the same signal replacement_ceiling already carries.
    demand['is_cliff'] is exposed separately as an awareness flag, not a score input.
    """
    undrafted = pool[~pool['drafted']]
    replacement = undrafted['position'].map(demand['replacement_ceiling'])
    return undrafted['ceiling_90'] - replacement


def effective_position_needs(settings: DraftSettings) -> dict[str, int]:
    """Personal roster-construction target per position: dedicated slots, plus
    one more for each shared FLEX/SUPER_FLEX slot type the position is
    eligible for. A superflex league's SUPER_FLEX slot isn't "any position" in
    practice - QB is usually the best play there - so QB's real personal
    target is 2 (1 dedicated + 1 for SUPER_FLEX), not 1. Same idea for
    RB/WR/TE against FLEX and SUPER_FLEX. Whole-player counts, since roster
    construction is naturally "how many of this position should I own",
    not a fractional share.
    """
    needs: dict[str, int] = {}
    for slot, count in settings.slots.items():
        if slot in ('FLEX', 'SUPER_FLEX'):
            for pos in SLOT_ELIGIBILITY[slot]:
                needs[pos] = needs.get(pos, 0) + count
        else:
            needs[slot] = needs.get(slot, 0) + count
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


def is_users_turn(draft: dict, picks_made: int, user_id: str) -> bool:
    """True if user_id is on the clock for the next pick. Auction drafts have no
    fixed turn order (nomination-based) so any user can always act."""
    if draft.get('type') == 'auction':
        return True
    teams = draft['settings']['teams']
    user_slot = (draft.get('draft_order') or {}).get(user_id)
    if user_slot is None:
        return False
    pick_no = picks_made + 1
    round_no = (pick_no - 1) // teams + 1
    pos_in_round = (pick_no - 1) % teams + 1
    if draft.get('type') == 'linear':
        on_clock_slot = pos_in_round
    else:  # snake (default draft type)
        on_clock_slot = pos_in_round if round_no % 2 == 1 else teams - pos_in_round + 1
    return on_clock_slot == user_slot


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
    @st.cache_data(ttl=METADATA_TTL)
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
    top5 = pool[~pool['drafted']].nlargest(5, 'personal_score').copy()
    top5['name'] = top5['first_name'] + ' ' + top5['last_name']
    top5['Cliff?'] = top5['position'].map(demand['is_cliff']).fillna(False)
    display = top5[['name', 'position', 'team', 'ceiling_90', 'bb_vorp', 'personal_score', 'Cliff?']]
    styled = (display.style
              .apply(_highlight_cliff_row, axis=1)
              .format({
                  'ceiling_90': '{:.1f}', 'bb_vorp': '{:.1f}', 'personal_score': '{:.1f}',
                  'Cliff?': lambda v: '\U0001f525 Cliff' if v else '',
              }))
    st.dataframe(styled, hide_index=True)


@st.fragment(run_every=DRAFT_TTL)
def _draft_assistant_fragment(draft_id: str, user_id: str):
    data = DraftData(draft_id=draft_id)
    settings = DraftSettings.from_draft(data.draft)
    scoring = fetch_draft_scoring(data.draft.get('league_id'))
    season = int(data.draft.get('season') or sleeper.get_sport_state('nfl')['league_season'])
    projections = build_season_projections(season, scoring)
    pool = build_player_pool(projections, settings, data.picks)
    demand = PositionDemand(pool, settings)
    pool = pool.assign(bb_vorp=compute_bb_vorp(pool, demand).reindex(pool.index))

    my_roster = build_my_roster(data.picks, user_id, projections)
    personal_score = compute_personal_score(pool, pool['bb_vorp'], my_roster, settings)
    pool = pool.assign(personal_score=personal_score.reindex(pool.index))

    st.caption(f"Pick {len(data.picks) + 1} on the clock \u00b7 refreshes every {DRAFT_TTL}s")
    if is_users_turn(data.draft, len(data.picks), user_id):
        st.success("It's your turn!")
    else:
        st.caption("Not your turn yet \u2014 best available shown below anyway.")
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
