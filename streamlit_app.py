import streamlit as st
import numpy as np
import pandas as pd
import requests
import re
from dataclasses import InitVar, dataclass, field
from itertools import combinations
from typing import Optional, List
from urllib.parse import quote
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


SLOT_ELIGIBILITY = {slot: set(eligible) for slot, _, eligible in Positions.MAPPINGS}


@st.cache_data(ttl=STATIC_TTL)
def get_sport_state(sport: str = 'nfl') -> dict:
    return sleeper.get_sport_state(sport)



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

    @classmethod
    def from_rosters(cls, rosters: pd.DataFrame) -> 'DraftSettings':
        """Infer starting slots from the most common roster composition across the league."""
        from collections import Counter
        pos_counts = Counter()
        players_df = Data.get_players()
        player_pos_map = players_df['position'].to_dict() if 'position' in players_df.columns else {}
        for _, roster in rosters.iterrows():
            for pos in roster.get('players', []):
                player = player_pos_map.get(pos)
                if player:
                    pos_counts[player] += 1
        # Normalize: divide by number of teams to get per-roster counts
        teams = len(rosters)
        slots = {pos: max(1, round(count / teams)) for pos, count in pos_counts.items()}
        return cls(teams=teams, slots=slots)

    @classmethod
    def from_actual_roster(cls, rosters: pd.DataFrame, roster_id: str) -> 'DraftSettings':
        """Infer starting slots from the user's own roster composition."""
        roster = rosters.loc[roster_id]
        players = roster.get('players', [])
        players_df = Data.get_players()
        player_pos_map = players_df['position'].to_dict() if 'position' in players_df.columns else {}
        pos_counts = {}
        for pid in players:
            pos = player_pos_map.get(pid)
            if pos:
                pos_counts[pos] = pos_counts.get(pos, 0) + 1
        teams = len(rosters)
        return cls(teams=teams, slots=pos_counts)

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
        if (
            self.injury_status
            and pd.notna(self.injury_status)
            and str(self.injury_status).strip().lower() not in ('nan', 'none', '')
        ):
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
        return Data.get_league(int(league_id)).get_league()['scoring_settings']
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
    p50_weekly = weekly.median(axis=1, skipna=True)
    p90_weekly = (weekly.mean(axis=1, skipna=True) +
                  Z_90TH_PERCENTILE * weekly.std(axis=1, skipna=True).fillna(0.0))
    return pd.DataFrame({
        'p50_weekly': p50_weekly,
        'p90_weekly': p90_weekly,
        'adp': adp,
    })



@st.cache_data(ttl=METADATA_TTL)
def get_user_leagues(username: str, season: int) -> tuple[str, list]:
    """Returns (user_id, leagues) for the given Sleeper username and season."""
    user = sleeper.User(username)
    return user.get_user_id(), user.get_all_leagues('nfl', season)
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











# Starting slots have disjoint eligibility; FLEX, SUPER_FLEX, then BN only widen it.
# Take the highest remaining projection for each slot without exploring player subsets.
def _slot_priority(slot: str) -> int:
    if slot in ('QB', 'RB', 'WR', 'TE', 'K', 'DEF'):
        return 1
    if slot in ('FLEX', 'FX'):
        return 2
    if slot in ('SUPER_FLEX', 'SFX'):
        return 3
    return 4


def _best_lineup_score(positions: pd.Series | list[str],
                       scores: pd.Series | list[float], slots: list[str]) -> float:
    if isinstance(positions, pd.Series):
        pos_vals = positions.to_numpy()
    else:
        pos_vals = np.asarray(positions)
    if isinstance(scores, pd.Series):
        index = positions.index if isinstance(positions, pd.Series) else range(len(pos_vals))
        score_vals = scores.reindex(index).fillna(0.0).to_numpy()
    else:
        score_vals = np.asarray(scores, dtype=float)

    order = np.argsort(-score_vals)
    sorted_pos = pos_vals[order]
    sorted_scores = score_vals[order]

    ordered_slots = sorted(slots, key=_slot_priority)
    total = 0.0
    used = np.zeros(len(order), dtype=bool)
    for slot in ordered_slots:
        eligible = SLOT_ELIGIBILITY.get(slot, [slot])
        for i in range(len(order)):
            if not used[i] and sorted_pos[i] in eligible:
                used[i] = True
                total += sorted_scores[i]
                break
    return float(total)


def compute_lineup_uplift(pool: pd.DataFrame, weekly_points: pd.DataFrame,
                           my_roster: pd.DataFrame, settings: DraftSettings,
                           playoff_week_start: int | None = None) -> pd.Series:
    """Aggregate weekly lineup value from upside inputs or base projections."""
    undrafted = pool[~pool['drafted']]
    uplift = pd.Series(0.0, index=undrafted.index)
    slots = [
        slot
        for slot, count in settings.slots.items()
        for _ in range(count)
    ]
    roster_positions = my_roster['position'].tolist() if not my_roster.empty else []
    roster_indices = my_roster.index.tolist() if not my_roster.empty else []
    weekly_dict = {w: weekly_points[w].to_dict() for w in weekly_points.columns}
    playoff_weight = 1.5 if playoff_week_start is not None else 1.0
    total_weight = 0.0
    for week in weekly_points.columns:
        weight = (playoff_weight
                  if playoff_week_start is not None and week >= playoff_week_start
                  else 1.0)
        total_weight += weight
        w_dict = weekly_dict.get(week, {})
        scores = [float(w_dict.get(pid, 0.0)) for pid in roster_indices]
        baseline = _best_lineup_score(roster_positions, scores, slots)
        without_slot = [
            _best_lineup_score(
                roster_positions, scores, slots[:index] + slots[index + 1:])
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
                uplift.loc[candidate_index] += weight * np.maximum(
                    0.0, candidate_scores.loc[candidate_index] +
                    max(eligible_scores) - baseline)
    return uplift / max(total_weight, 1.0)


SCARCITY_WEIGHT = 1.0  # per-point erosion in replacement value one round later
UPSIDE_WEIGHT = 0.15    # per-point gap between a player's P90 and P50 week


def compute_replacement_level(pool: pd.DataFrame, lineup_uplift: pd.Series,
                              pick_number: int) -> pd.Series:
    """Best lineup_uplift available at each position among undrafted players
    not yet on the board (ADP after pick_number) - what you could still get."""
    undrafted = pool.loc[~pool['drafted']]
    candidates = undrafted.loc[undrafted['adp'].gt(pick_number)]
    if candidates.empty:
        return pd.Series(dtype=float)
    replacements = candidates.loc[candidates.groupby('position')['adp'].idxmin()]
    return pd.Series(
        lineup_uplift.reindex(replacements.index).to_numpy(),
        index=replacements['position'])


def compute_lineup_vorp(pool: pd.DataFrame, lineup_uplift: pd.Series,
                        next_pick_number: int) -> pd.Series:
    undrafted = pool.loc[~pool['drafted']]
    replacement = compute_replacement_level(pool, lineup_uplift, next_pick_number)
    return (lineup_uplift.reindex(undrafted.index) -
            undrafted['position'].map(replacement).fillna(0.0))


def compute_position_scarcity(pool: pd.DataFrame, lineup_uplift: pd.Series,
                              next_pick_number: int, teams: int) -> pd.Series:
    """Per-position value lost by waiting one more full round: how fast the
    replacement tier is drying up. Positive means a run risk worth reaching for now."""
    rep_now = compute_replacement_level(pool, lineup_uplift, next_pick_number)
    rep_later = compute_replacement_level(pool, lineup_uplift, next_pick_number + teams)
    common = rep_now.index.intersection(rep_later.index)
    return (rep_now.reindex(common) - rep_later.reindex(common)).clip(lower=0.0)


def compute_upside_bonus(pool: pd.DataFrame) -> pd.Series:
    """Ceiling above a typical week - rewards boom potential that a
    median-week lineup_uplift alone doesn't capture."""
    undrafted = pool.loc[~pool['drafted']]
    return (undrafted['p90_weekly'] - undrafted['p50_weekly']).clip(lower=0.0)


def compute_draft_priority(pool: pd.DataFrame, lineup_vorp: pd.Series,
                           scarcity: pd.Series, upside_bonus: pd.Series) -> pd.Series:
    undrafted = pool.loc[~pool['drafted']]
    scarcity_bonus = undrafted['position'].map(scarcity).fillna(0.0)
    return (lineup_vorp.reindex(undrafted.index) +
            SCARCITY_WEIGHT * scarcity_bonus +
            UPSIDE_WEIGHT * upside_bonus.reindex(undrafted.index).fillna(0.0))


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

    def __init__(self, league_ids: list[str]):
        current = get_sport_state('nfl')
        self.username = st.query_params.get('username')
        self.season = int(current['league_season'])
        is_regular_season = current['season_type'] == 'regular'
        display_week = int(current['display_week'])
        self.week = st.session_state.get(
            'week') or (display_week if is_regular_season and display_week > 0 else 1)
        self.leagues = []
        for league_id in league_ids:
            data = Data(league_id=league_id, context=self)
            self.leagues.append(League(data=data))


def render_my_roster(my_roster: pd.DataFrame):
    st.subheader("Your Roster So Far")
    if my_roster.empty:
        st.caption("No picks yet.")
        return
    counts = my_roster['position'].value_counts().sort_index()
    positions = ", ".join(f"{pos} {count}" for pos, count in counts.items())
    st.caption(f"Position counts: {positions}")
    display = my_roster.copy()
    display['name'] = display['first_name'] + ' ' + display['last_name']
    cols = ['name', 'position', 'team', 'bye_week']
    st.dataframe(
        display[cols].sort_values('position'),
        hide_index=True,
        column_order=cols,
    )



def render_recommendations(pool: pd.DataFrame):
    st.subheader("Top 5 Recommendations")
    top5 = pool[~pool['drafted']].sort_values(
        ['draft_priority', 'p90_weekly'], ascending=False).head(5).copy()
    top5['name'] = top5['first_name'] + ' ' + top5['last_name']
    display = top5[['name', 'position', 'team', 'p50_weekly', 'p90_weekly',
                    'lineup_vorp', 'scarcity_bonus', 'upside_bonus', 'draft_priority']]
    styled = display.style.format({
        'p50_weekly': '{:.1f}', 'p90_weekly': '{:.1f}', 'lineup_vorp': '{:.1f}',
        'scarcity_bonus': '{:.1f}', 'upside_bonus': '{:.1f}', 'draft_priority': '{:.1f}',
    })
    st.dataframe(styled, hide_index=True, column_order=display.columns.tolist())


@st.fragment(run_every=DRAFT_TTL)
def _draft_assistant_fragment(draft_id: str, user_id: str):
    data = DraftData(draft_id=draft_id)
    settings = DraftSettings.from_draft(data.draft)
    scoring = fetch_draft_scoring(data.draft.get('league_id'))
    season = int(data.draft.get('season') or get_sport_state('nfl')['league_season'])
    weekly_points, _ = build_projection_inputs(season, scoring)
    projections = build_season_projections(season, scoring)
    bye_weeks = Data.get_bye_weeks(season)
    pool = build_player_pool(projections, settings, data.picks, bye_weeks)
    next_pick_number = next_user_pick_number(
        data.draft, len(data.picks), user_id)
    users_turn = is_users_turn(data.draft, len(data.picks), user_id)
    my_roster = build_my_roster(data.picks, user_id, bye_weeks)
    playoff_week_start = data.draft.get('settings', {}).get('playoff_week_start')
    lineup_uplift = compute_lineup_uplift(
        pool, weekly_points, my_roster, settings, playoff_week_start)
    lineup_vorp = compute_lineup_vorp(pool, lineup_uplift, next_pick_number)
    scarcity = compute_position_scarcity(
        pool, lineup_uplift, next_pick_number, settings.teams)
    upside_bonus = compute_upside_bonus(pool)
    draft_priority = compute_draft_priority(pool, lineup_vorp, scarcity, upside_bonus)
    undrafted_positions = pool.loc[~pool['drafted'], 'position']
    pool = pool.assign(
        lineup_uplift=lineup_uplift.reindex(pool.index).fillna(0.0),
        lineup_vorp=lineup_vorp.reindex(pool.index),
        scarcity_bonus=undrafted_positions.map(scarcity).reindex(pool.index).fillna(0.0),
        upside_bonus=upside_bonus.reindex(pool.index).fillna(0.0),
        draft_priority=draft_priority.reindex(pool.index))

    st.caption(f"Pick {len(data.picks) + 1} on the clock · refreshes every {DRAFT_TTL}s")
    st.caption(
        f"Priority = lineup VORP (vs. first same-position ADP after your next "
        f"pick, Pick {next_pick_number}) + scarcity (value lost waiting one more "
        f"round) + upside (P90 ceiling above a typical week).")
    if users_turn:
        st.success("It's your turn!")
    else:
        st.caption("Not your turn yet — best available shown below anyway.")
    render_my_roster(my_roster)
    render_recommendations(pool)


def render_draft_assistant(username: str):
    st.title("Draft Recommendation Engine \U0001f3af")
    if not username:
        st.info("Enter your Sleeper username above to find your drafts.")
        return

    season = int(get_sport_state('nfl')['league_season'])
    try:
        user_id, drafts = get_user_drafts(username, season)
    except Exception as exc:  # noqa: BLE001 - surface any Sleeper lookup failure
        st.error(
            f"Could not load drafts for Sleeper user '{username}'. "
            f"Check the username, or retry if Sleeper is unavailable. ({exc})")
        return

    if not drafts:
        st.info("No drafts found for this user this season.")
        return

    for draft in drafts:
        draft_id = draft['draft_id']
        name = draft.get('metadata', {}).get('name') or draft_id
        st.markdown(f"## {name}")
        _draft_assistant_fragment(draft_id, user_id)
        st.markdown(f"(Draft ID: {draft_id})")

@dataclass
class WaiverData:
    league_id: InitVar[int]
    week: InitVar[int]
    rosters: pd.DataFrame = None
    users: pd.DataFrame = None
    transactions: pd.DataFrame = None
    _league: sleeper.League = field(default=None, init=False, repr=False)

    def __post_init__(self, league_id: int, week: int):
        self._league = Data.get_league(league_id)
        if self.rosters is None:
            self.rosters = pd.json_normalize(self._league.get_rosters()).set_index('roster_id')
        if self.users is None:
            self.users = pd.json_normalize(self._league.get_users())
            if 'user_id' in self.users.columns:
                self.users.set_index('user_id', inplace=True)
        if self.transactions is None:
            self.transactions = pd.DataFrame(self._league.get_transactions(week))

    @property
    def waiver_priority(self) -> list[str]:
        """Return roster_ids ordered by current waiver priority (1 = first to spend)."""
        return list(self.rosters.index)

    @property
    def waiver_settings(self) -> dict:
        return self._league.get_league().get('settings', {})

    def get_free_agent_player_ids(self, all_player_ids: set) -> set:
        """Players not on any roster in the league."""
        owned = set()
        for _, roster in self.rosters.iterrows():
            owned.update(roster.get('players', []))
        return all_player_ids - owned

    def get_user_roster_id(self, user_id: str) -> Optional[str]:
        for rid, row in self.rosters.iterrows():
            if row.get('owner_id') == user_id:
                return rid
        return None
    def get_user_waiver_rank(self, user_id: str) -> int:
        for rank, rid in enumerate(self.waiver_priority, 1):
            if self.rosters.loc[rid, 'owner_id'] == user_id:
                return rank
        return len(self.waiver_priority)


def build_waiver_pool(projections: pd.DataFrame, settings: DraftSettings,
                      free_agent_ids: set, bye_weeks: dict[str, int]) -> pd.DataFrame:
    """Build a pool of free agents with projection and metadata."""
    players = Data.get_players()[['position', 'first_name', 'last_name', 'team']]
    pool = projections.join(players, how='inner')
    pool = pool[pool['position'].isin(settings.relevant_positions)]
    pool = pool.reindex(list(free_agent_ids)).dropna()
    return pool.assign(
        bye_week=pool['team'].map(bye_weeks),
        drafted=False,
    )


def compute_waiver_value(pool: pd.DataFrame, lineup_uplift: pd.Series,
                         my_roster: pd.DataFrame, settings: DraftSettings,
                         waiver_rank: int, teams: int,
                         playoff_week_start: int | None = None) -> pd.DataFrame:
    """Compute waiver recommendation scores for free agents.

    Waiver value = lineup uplift (how much better this player makes your
    best-week lineup) + upside bonus (P90 ceiling for boom weeks).
    """

    # Use pre-computed lineup_uplift; skip internal week recomputation.
    uplift = lineup_uplift.reindex(pool.index).fillna(0.0)

    my_roster_ids = my_roster.index.tolist()
    if not my_roster_ids:
        pool = pool.assign(drafted=False)
        upside_bonus = compute_upside_bonus(pool)
        waiver_priority = uplift + UPSIDE_WEIGHT * upside_bonus.reindex(pool.index).fillna(0.0)
        return pool.assign(
            lineup_uplift=pd.Series(0.0, index=pool.index),
            waiver_vorp=pd.Series(0.0, index=pool.index),
            waiver_scarcity=pd.Series(0.0, index=pool.index),
            upside_bonus=upside_bonus.reindex(pool.index).fillna(0.0),
            waiver_priority=waiver_priority,
        )

    pool = pool.assign(drafted=False)
    upside_bonus = compute_upside_bonus(pool)

    waiver_vorp = uplift
    waiver_priority = uplift + UPSIDE_WEIGHT * upside_bonus.reindex(pool.index).fillna(0.0)

    return pool.assign(
        lineup_uplift=uplift,
        waiver_vorp=waiver_vorp,
        waiver_scarcity=pd.Series(0.0, index=pool.index),
        upside_bonus=upside_bonus.reindex(pool.index).fillna(0.0),
        waiver_priority=waiver_priority,
    )


def compute_waiver_add_drop_recommendations(
    waiver_pool: pd.DataFrame,
    weekly_points: pd.DataFrame,
    my_roster: pd.DataFrame,
    settings: DraftSettings,
    projections: pd.DataFrame = None,
    playoff_week_start: int | None = None,
    current_week: int = 1,
) -> pd.DataFrame:
    """Compute add/drop recommendations that strictly improve the team (uplift > 0).

    For each free agent candidate A in waiver_pool and each roster player D in my_roster,
    computes the net team lineup score uplift across rest of season weeks (>= current_week)
    when dropping D and adding A. Identifies the drop player D that maximizes net uplift
    for candidate A, and filters out any recommendations with net uplift <= 0.
    """
    if waiver_pool.empty:
        return pd.DataFrame()

    slots = [
        slot
        for slot, count in settings.slots.items()
        for _ in range(count)
    ]

    weeks = [w for w in weekly_points.columns if w in SEASON_WEEKS and w >= current_week]
    if not weeks:
        return pd.DataFrame()

    playoff_weight = 1.5 if playoff_week_start is not None else 1.0
    weights = {
        w: (playoff_weight if playoff_week_start is not None and w >= playoff_week_start else 1.0)
        for w in weeks
    }
    total_weight = sum(weights.values())

    weekly_points_dict = {
        w: weekly_points[w].to_dict()
        for w in weeks
        if w in weekly_points.columns
    }

    roster_indices = my_roster.index.tolist() if not my_roster.empty else []
    roster_positions = my_roster['position'].tolist() if not my_roster.empty else []

    baseline_scores = {}
    baseline_minus_D = {}
    without_slot_minus_D = {}

    for w in weeks:
        w_dict = weekly_points_dict.get(w, {})
        if roster_indices:
            r_scores = [float(w_dict.get(rid, 0.0)) for rid in roster_indices]
            baseline_scores[w] = _best_lineup_score(roster_positions, r_scores, slots)

            for d_idx, d_id in enumerate(roster_indices):
                sub_positions = roster_positions[:d_idx] + roster_positions[d_idx + 1:]
                sub_scores = r_scores[:d_idx] + r_scores[d_idx + 1:]
                baseline_minus_D[(w, d_id)] = _best_lineup_score(sub_positions, sub_scores, slots)
                without_slot_minus_D[(w, d_id)] = [
                    _best_lineup_score(sub_positions, sub_scores, slots[:i] + slots[i + 1:])
                    for i in range(len(slots))
                ]
        else:
            baseline_scores[w] = 0.0

    if projections is None:
        projections = pd.DataFrame()

    unique_candidate_positions = waiver_pool['position'].unique()
    eligible_indices_by_pos = {
        pos: [i for i, s in enumerate(slots) if pos in SLOT_ELIGIBILITY[s]]
        for pos in unique_candidate_positions
    }

    max_without_slot = {}
    for pos_A, elig_idx in eligible_indices_by_pos.items():
        if elig_idx:
            for (w, d_id), w_slots in without_slot_minus_D.items():
                max_without_slot[(w, d_id, pos_A)] = max(w_slots[i] for i in elig_idx)

    recs = []

    for a_id, a_row in waiver_pool.iterrows():
        pos_A = a_row['position']
        elig_idx = eligible_indices_by_pos[pos_A]

        a_first = a_row.get('first_name', '')
        a_last = a_row.get('last_name', '')
        a_name = f"{a_first} {a_last}".strip() if (a_first or a_last) else str(a_id)
        a_team = a_row.get('team', '')
        a_p50 = float(a_row.get('p50_weekly', projections.loc[a_id, 'p50_weekly'] if a_id in projections.index else 0.0))
        a_p90 = float(a_row.get('p90_weekly', projections.loc[a_id, 'p90_weekly'] if a_id in projections.index else 0.0))

        if roster_indices:
            best_d_id = None
            best_uplift = -float('inf')

            for d_id in roster_indices:
                weighted_uplift_sum = 0.0
                for w in weeks:
                    w_dict = weekly_points_dict.get(w, {})
                    score_A = float(w_dict.get(a_id, 0.0))
                    base_sub = baseline_minus_D[(w, d_id)]
                    if elig_idx:
                        max_slot = max_without_slot[(w, d_id, pos_A)]
                        new_score = max(base_sub, max_slot + score_A)
                    else:
                        new_score = base_sub
                    net_w = new_score - baseline_scores[w]
                    weighted_uplift_sum += weights[w] * net_w

                avg_uplift = weighted_uplift_sum / total_weight
                if avg_uplift > best_uplift:
                    best_uplift = avg_uplift
                    best_d_id = d_id

            if best_uplift > 0 and best_d_id is not None:
                d_row = my_roster.loc[best_d_id]
                d_first = d_row.get('first_name', '')
                d_last = d_row.get('last_name', '')
                d_name = f"{d_first} {d_last}".strip() if (d_first or d_last) else str(best_d_id)
                d_pos = d_row.get('position', '')
                d_team = d_row.get('team', '')
                d_p50 = float(d_row.get('p50_weekly', projections.loc[best_d_id, 'p50_weekly'] if best_d_id in projections.index else 0.0))
                d_p90 = float(d_row.get('p90_weekly', projections.loc[best_d_id, 'p90_weekly'] if best_d_id in projections.index else 0.0))

                recs.append({
                    'add_player_id': a_id,
                    'add_name': a_name,
                    'add_position': pos_A,
                    'add_team': a_team,
                    'add_p50': a_p50,
                    'add_p90': a_p90,
                    'drop_player_id': best_d_id,
                    'drop_name': d_name,
                    'drop_position': d_pos,
                    'drop_team': d_team,
                    'drop_p50': d_p50,
                    'drop_p90': d_p90,
                    'uplift': best_uplift,
                })
        else:
            weighted_uplift_sum = 0.0
            for w in weeks:
                w_dict = weekly_points_dict.get(w, {})
                score_A = float(w_dict.get(a_id, 0.0))
                new_score = score_A if elig_idx else 0.0
                weighted_uplift_sum += weights[w] * new_score

            avg_uplift = weighted_uplift_sum / total_weight
            if avg_uplift > 0:
                recs.append({
                    'add_player_id': a_id,
                    'add_name': a_name,
                    'add_position': pos_A,
                    'add_team': a_team,
                    'add_p50': a_p50,
                    'add_p90': a_p90,
                    'drop_player_id': None,
                    'drop_name': 'None',
                    'drop_position': '',
                    'drop_team': '',
                    'drop_p50': 0.0,
                    'drop_p90': 0.0,
                    'uplift': avg_uplift,
                })

    df = pd.DataFrame(recs)
    if not df.empty:
        df.sort_values(by='uplift', ascending=False, inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


def compute_trade_recommendations(
    my_roster: pd.DataFrame,
    opponent_rosters: dict[str, dict],
    weekly_points: pd.DataFrame,
    settings: DraftSettings,
    projections: pd.DataFrame = None,
    playoff_week_start: int | None = None,
    current_week: int = 1,
) -> pd.DataFrame:
    """Find win-win swaps of one or two players per team across remaining weeks.

    Every single-player swap is scored. Package searches use the eight highest
    projected players on each roster to bound the pairwise combinations.
    """
    if my_roster.empty or not opponent_rosters:
        return pd.DataFrame()

    slots = [slot for slot, count in settings.slots.items() for _ in range(count)]
    weeks = [w for w in weekly_points.columns if w in SEASON_WEEKS and w >= current_week]
    if not weeks:
        return pd.DataFrame()

    weights = np.array([1.5 if playoff_week_start is not None and w >= playoff_week_start else 1.0
                        for w in weeks])
    total_weight = weights.sum()
    scores = [weekly_points[w].fillna(0.0).to_dict() for w in weeks]
    if projections is None:
        projections = pd.DataFrame()

    def player_info(roster):
        info = {}
        for player_id, row in roster.iterrows():
            first, last = row.get('first_name', ''), row.get('last_name', '')
            projected = projections.loc[player_id] if player_id in projections.index else {}
            p50 = row.get('p50_weekly', projected.get('p50_weekly', 0.0))
            p90 = row.get('p90_weekly', projected.get('p90_weekly', 0.0))
            info[player_id] = {
                'id': player_id,
                'name': f"{first} {last}".strip() or str(player_id),
                'position': row['position'],
                'team': row.get('team', ''),
                'p50': float(p50) if pd.notna(p50) else 0.0,
                'p90': float(p90) if pd.notna(p90) else 0.0,
            }
        return info

    def packages(roster):
        ids = roster.index.tolist()
        ranked = sorted(ids, key=lambda pid: sum(weight * week.get(pid, 0.0)
                                                  for weight, week in zip(weights, scores)), reverse=True)
        return [(pid,) for pid in ids] + list(combinations(ranked[:8], 2))

    def roster_states(roster, info, choices):
        ids = roster.index.tolist()
        baseline = [_best_lineup_score(roster['position'],
                                       [week.get(pid, 0.0) for pid in ids], slots)
                    for week in scores]
        states = {}
        for outgoing in choices:
            removed = set(outgoing)
            remaining = [pid for pid in ids if pid not in removed]
            states[outgoing] = (
                np.array([info[pid]['position'] for pid in remaining]),
                np.array([info[pid]['position'] for pid in outgoing]),
                [(np.array([week.get(pid, 0.0) for pid in remaining]),
                  np.array([week.get(pid, 0.0) for pid in outgoing])) for week in scores],
            )
        return baseline, states

    my_info = player_info(my_roster)
    my_choices = packages(my_roster)
    my_baseline, my_states = roster_states(my_roster, my_info, my_choices)
    recs = []
    for opp_id, opp_data in opponent_rosters.items():
        opp_roster = opp_data.get('roster')
        if opp_roster is None or opp_roster.empty:
            continue
        opp_name = opp_data.get('name') or opp_data.get('username') or str(opp_id)
        opp_info = player_info(opp_roster)
        opp_choices = packages(opp_roster)
        opp_baseline, opp_states = roster_states(opp_roster, opp_info, opp_choices)

        for give in my_choices:
            my_pos, give_pos, my_weeks = my_states[give]
            for receive in opp_choices:
                opp_pos, receive_pos, opp_weeks = opp_states[receive]
                new_my_pos = np.concatenate((my_pos, receive_pos))
                new_opp_pos = np.concatenate((opp_pos, give_pos))
                my_sum = partner_sum = 0.0
                for i, weight in enumerate(weights):
                    my_remaining, given_scores = my_weeks[i]
                    opp_remaining, received_scores = opp_weeks[i]
                    new_my = _best_lineup_score(new_my_pos,
                                                np.concatenate((my_remaining, received_scores)), slots)
                    new_partner = _best_lineup_score(new_opp_pos,
                                                     np.concatenate((opp_remaining, given_scores)), slots)
                    my_sum += weight * (new_my - my_baseline[i])
                    partner_sum += weight * (new_partner - opp_baseline[i])
                if my_sum <= 0 or partner_sum <= 0:
                    continue

                my_uplift = my_sum / total_weight
                partner_uplift = partner_sum / total_weight
                single = len(give) == len(receive) == 1
                d = my_info[give[0]]
                a = opp_info[receive[0]]
                recs.append({
                    'partner_id': opp_id,
                    'partner_name': opp_name,
                    'give_players': tuple(my_info[pid] for pid in give),
                    'receive_players': tuple(opp_info[pid] for pid in receive),
                    'give_player_id': d['id'] if single else None,
                    'give_name': d['name'] if single else None,
                    'give_position': d['position'] if single else None,
                    'give_team': d['team'] if single else None,
                    'give_p50': d['p50'] if single else None,
                    'give_p90': d['p90'] if single else None,
                    'receive_player_id': a['id'] if single else None,
                    'receive_name': a['name'] if single else None,
                    'receive_position': a['position'] if single else None,
                    'receive_team': a['team'] if single else None,
                    'receive_p50': a['p50'] if single else None,
                    'receive_p90': a['p90'] if single else None,
                    'my_uplift': my_uplift,
                    'partner_uplift': partner_uplift,
                    'total_uplift': my_uplift + partner_uplift,
                })

    df = pd.DataFrame(recs)
    if not df.empty:
        df.sort_values(by=['my_uplift', 'partner_uplift'], ascending=[False, False], inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


def sleeper_player_url(name: str, player_id: str) -> str:
    """Sleeper web profile URL for a player (not the JSON endpoint)."""
    if not player_id:
        return ''
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return f"https://sleeper.com/nfl/players/{slug}-{quote(str(player_id), safe='')}"


def sleeper_player_link(name: str, player_id: str) -> str:
    """Link to the Sleeper web profile, not the player JSON endpoint."""
    if not player_id:
        return f"**{name}**"
    return f"[{name}]({sleeper_player_url(name, player_id)})"


def compact_styles() -> Style:
    """Shared table styling for the compact recommendation views."""
    return Style({
        'table': {'width': '100%', 'max-width': '600px', 'table-layout': 'fixed',
                  'font-size': '0.9em'},
        'header': {'font-size': '0.6em', 'line-height': '1em', 'opacity': '0.6',
                   'text-align': 'left', 'white-space': 'nowrap'},
        'headnum': {'font-size': '0.6em', 'line-height': '1em', 'opacity': '0.6',
                    'text-align': 'right', 'white-space': 'nowrap'},
        'name': {'line-height': '1.2em', 'text-overflow': 'ellipsis',
                 'overflow': 'hidden', 'white-space': 'nowrap'},
        'link': {'color': 'inherit', 'text-decoration': 'none'},
        'info': {'font-size': '0.8em', 'line-height': '0.9em', 'opacity': '0.8',
                 'text-overflow': 'ellipsis', 'overflow': 'hidden', 'white-space': 'nowrap'},
        'num': {'line-height': '1.2em', 'text-align': 'right'},
        'gain': {'line-height': '1.2em', 'text-align': 'right', 'font-weight': 'bold'},
        'label': {'text-align': 'center', 'vertical-align': 'middle', 'font-size': '0.6em',
                  'opacity': '0.8'},
        'status': {'font-size': '0.8em', 'font-style': 'italic', 'line-height': '1em',
                   'opacity': '0.6'},
    })


def render_waiver_pool(recommendations: pd.DataFrame):
    """Render the best adds under the player each would replace."""
    st.subheader("Recommended moves")
    if recommendations.empty:
        st.info("No lineup-improving waiver moves this week.")
        return

    recs = recommendations.sort_values(by='uplift', ascending=False) if 'uplift' in recommendations.columns else recommendations
    drop_groups = {}
    for _, row in recs.iterrows():
        drop_id = row.get('drop_player_id')
        if drop_id not in drop_groups:
            drop_groups[drop_id] = {
                'drop_name': row.get('drop_name', 'None'),
                'drop_position': row.get('drop_position', ''),
                'drop_team': row.get('drop_team', ''),
                'drop_p50': row.get('drop_p50', 0.0),
                'drop_p90': row.get('drop_p90', 0.0),
                'adds': [],
            }
        drop_groups[drop_id]['adds'].append(row)

    s = compact_styles()
    for drop_id, group in drop_groups.items():
        if drop_id and group['drop_name'] != 'None':
            pos_team = f"{group['drop_position']} - {group['drop_team']}".strip(' -')
            drop_info = f"Drop **{group['drop_name']}**" + (f" ({pos_team})" if pos_team else "")
            if group['drop_p50'] > 0 or group['drop_p90'] > 0:
                drop_info += f" · P50 {group['drop_p50']:.1f} · P90 {group['drop_p90']:.1f}"
        else:
            drop_info = "Add Without Dropping"

        st.markdown(f"#### {drop_info}")
        doc, tag, text, line = Doc().ttl()
        with tag('table', style=s.table):
            with tag('tbody'):
                with tag('tr'):
                    line('th', 'Add', style=s.header)
                    line('th', 'P50', style=s.headnum)
                    line('th', 'P90', style=s.headnum)
                    line('th', 'Gain', style=s.headnum)
                for add_row in group['adds']:
                    add_id = add_row.get('add_player_id', '')
                    add_name = add_row.get('add_name', 'Unknown Player')
                    add_pos = add_row.get('add_position', '')
                    add_team = add_row.get('add_team', '')
                    add_p50 = add_row.get('add_p50', 0.0)
                    add_p90 = add_row.get('add_p90', 0.0)
                    uplift = add_row.get('uplift', 0.0)

                    with tag('tr'):
                        with tag('td', style=s.name):
                            with tag('a', href=sleeper_player_url(add_name, add_id), style=s.link):
                                text(add_name)
                        line('td', f"{add_p50:.1f}", style=s.num)
                        line('td', f"{add_p90:.1f}", style=s.num)
                        line('td', f"+{uplift:.2f}", style=s.gain)
                    with tag('tr'):
                        line('td', f"{add_pos} - {add_team}".strip(' -'),
                             colspan=4, style=s.info)
        st.html(doc.getvalue())


@st.fragment
def _waiver_guide_league_fragment(league_id: str, user_id: str, season: int, week: int):
    try:
        waiver_data = WaiverData(league_id=int(league_id), week=week)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load league data: {exc}")
        return

    roster_id = waiver_data.get_user_roster_id(user_id)
    if roster_id is None:
        st.warning("You do not have a roster in this league.")
        return

    user_roster = waiver_data.rosters.loc[[roster_id]]
    user_players = user_roster['players'].iloc[0]
    league = Data.get_league(int(league_id))
    try:
        settings = DraftSettings.from_draft(league.get_league())
    except (KeyError, AttributeError):
        settings = DraftSettings.from_actual_roster(waiver_data.rosters, roster_id)
    scoring = fetch_draft_scoring(str(league_id))
    bye_weeks = Data.get_bye_weeks(season)

    projections = build_season_projections(season, scoring)
    all_player_ids = set(Data.get_players().index)
    free_agent_ids = waiver_data.get_free_agent_player_ids(all_player_ids)

    if not free_agent_ids:
        st.info("No free agents available — all players are on rosters.")
        return

    waiver_pool = build_waiver_pool(projections, settings, free_agent_ids, bye_weeks)
    if waiver_pool.empty:
        st.info("No free agents available at your league's starting positions.")
        return

    my_roster = build_my_roster([], user_id, bye_weeks)
    if user_players:
        my_roster = Data.get_players()[['position', 'first_name', 'last_name', 'team']].loc[user_players]
        my_roster['bye_week'] = my_roster['team'].map(bye_weeks)

    my_roster = my_roster.join(projections[['p50_weekly', 'p90_weekly']], how='left')
    my_roster['p50_weekly'] = my_roster['p50_weekly'].fillna(0.0)
    my_roster['p90_weekly'] = my_roster['p90_weekly'].fillna(0.0)

    waiver_rank = waiver_data.get_user_waiver_rank(user_id)
    playoff_week_start = waiver_data.waiver_settings.get('playoff_week_start')

    weekly_points, _ = build_projection_inputs(season, scoring)
    recs = compute_waiver_add_drop_recommendations(
        waiver_pool, weekly_points, my_roster, settings,
        projections=projections, playoff_week_start=playoff_week_start,
        current_week=week)

    st.caption(f"Week {week} · Waiver rank #{waiver_rank} of {settings.teams}")
    st.caption(
        f"Showing recommendations that improve your team's projected lineup score.")
    render_waiver_pool(recs)


def render_waiver_guide(username: str, week: int):
    st.title("Waiver Guide \U0001f4dd")
    if not username:
        st.info("Enter your Sleeper username above to find your leagues.")
        return

    season = int(get_sport_state('nfl')['league_season'])
    try:
        user_id, all_leagues = get_user_leagues(username, season)
    except Exception as exc:  # noqa: BLE001
        st.error(
            f"Could not find Sleeper user '{username}'. "
            f"Check the username, or retry if Sleeper is unavailable. ({exc})")
        return

    if not all_leagues:
        st.info("No leagues found for this user this season.")
        return

    for l in all_leagues:
        league_id = l['league_id']
        name = l.get('name') or league_id
        st.markdown(f"## {name}")
        _waiver_guide_league_fragment(league_id, user_id, season, week)
        st.markdown(f"(League ID: {league_id})")


def render_trade_suggestions_table(recommendations: pd.DataFrame):
    """Show the strongest win-win offers under each trade partner."""
    st.subheader("Trade ideas by partner")
    if recommendations.empty:
        st.info("No mutually beneficial trade suggestions found.")
        return

    s = compact_styles()

    def side_rows(tag, text, line, players):
        """One row per player: name, then position/team and P50/P90 figures."""
        for player in players:
            with tag('tr'):
                with tag('td', style=s.name):
                    with tag('a', href=sleeper_player_url(player['name'], player['id']), style=s.link):
                        text(player['name'])
                line('td', f"{player['position']} {player['team']}", style=s.info)
                line('td', f"{player['p50']:.1f}", style=s.num)
                line('td', f"{player['p90']:.1f}", style=s.num)
        line('tr', '')

    for _, offers in recommendations.groupby('partner_id', sort=False):
        partner = offers.iloc[0]['partner_name']
        st.markdown(f"#### {partner} · top {min(len(offers), 5)} of {len(offers)}")

        doc, tag, text, line = Doc().ttl()
        with tag('table', style=s.table):
            with tag('tbody'):
                for _, offer in offers.head(5).iterrows():
                    give_players, receive_players = offer['give_players'], offer['receive_players']
                    with tag('tr'):
                        line('th', 'You give', colspan=2, style=s.header)
                        line('th', 'You receive', colspan=2, style=s.header)
                    side_rows(tag, text, line, give_players)
                    side_rows(tag, text, line, receive_players)
                    with tag('tr'):
                        line('td', f"You gain {offer['my_uplift']:+.1f} pts/wk",
                             colspan=2, style=s.status)
                        line('td', f"Their gain {offer['partner_uplift']:+.1f} pts/wk",
                             colspan=2, style=s.status)
                    line('tr', '')
        st.html(doc.getvalue())
        if any(len(o['give_players']) != len(o['receive_players'])
               for _, o in offers.head(5).iterrows()):
            st.caption("Uneven trade · the team receiving more players may need to free a roster spot.")


def _trade_suggestions_league_fragment(league_id: str, user_id: str, season: int, week: int):
    try:
        waiver_data = WaiverData(league_id=int(league_id), week=week)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load league data: {exc}")
        return

    user_roster_id = waiver_data.get_user_roster_id(user_id)
    if user_roster_id is None:
        st.warning("You do not have a roster in this league.")
        return

    league = sleeper.League(int(league_id))
    try:
        settings = DraftSettings.from_draft(league.get_league())
    except (KeyError, AttributeError):
        settings = DraftSettings.from_actual_roster(waiver_data.rosters, user_roster_id)

    scoring = fetch_draft_scoring(str(league_id))
    bye_weeks = Data.get_bye_weeks(season)

    projections = build_season_projections(season, scoring)
    weekly_points, _ = build_projection_inputs(season, scoring)

    rosters_info = Data.get_rosters(int(league_id))
    user_players = waiver_data.rosters.loc[user_roster_id, 'players'] if 'players' in waiver_data.rosters.columns else []

    my_roster = build_my_roster([], user_id, bye_weeks)
    if user_players:
        my_roster = Data.get_players()[['position', 'first_name', 'last_name', 'team']].reindex(user_players).dropna(subset=['position'])
        my_roster['bye_week'] = my_roster['team'].map(bye_weeks)

    my_roster = my_roster.join(projections[['p50_weekly', 'p90_weekly']], how='left')
    my_roster['p50_weekly'] = my_roster['p50_weekly'].fillna(0.0)
    my_roster['p90_weekly'] = my_roster['p90_weekly'].fillna(0.0)

    opponent_rosters = {}
    for rid, row in waiver_data.rosters.iterrows():
        if rid == user_roster_id:
            continue
        opp_players = row.get('players', [])
        if not opp_players:
            continue
        opp_roster = Data.get_players()[['position', 'first_name', 'last_name', 'team']].reindex(opp_players).dropna(subset=['position'])
        opp_roster['bye_week'] = opp_roster['team'].map(bye_weeks)
        opp_roster = opp_roster.join(projections[['p50_weekly', 'p90_weekly']], how='left')
        opp_roster['p50_weekly'] = opp_roster['p50_weekly'].fillna(0.0)
        opp_roster['p90_weekly'] = opp_roster['p90_weekly'].fillna(0.0)

        partner_name = f"Team {rid}"
        partner_username = ''
        if rid in rosters_info.index:
            r_info = rosters_info.loc[rid]
            partner_name = r_info.get('name') or r_info.get('username') or partner_name
            partner_username = r_info.get('username') or ''

        opponent_rosters[rid] = {
            'name': partner_name,
            'username': partner_username,
            'roster': opp_roster,
        }

    playoff_week_start = waiver_data.waiver_settings.get('playoff_week_start')

    recs = compute_trade_recommendations(
        my_roster, opponent_rosters, weekly_points, settings,
        projections=projections, playoff_week_start=playoff_week_start,
        current_week=week)

    st.caption(f"Week {week} · Trade Analyzer")
    st.caption(
        "Win-win offers improve both teams' projected rest-of-season lineups. "
        "Every 1-for-1 is evaluated; two-player packages use each team's "
        "eight highest-projected candidates.")
    render_trade_suggestions_table(recs)


def render_trade_suggestions(username: str, week: int):
    st.title("Trade Suggestions \U0001f91d")
    if not username:
        st.info("Enter your Sleeper username in the sidebar to find your leagues.")
        return

    season = int(sleeper.get_sport_state('nfl')['league_season'])
    try:
        user_id, all_leagues = get_user_leagues(username, season)
    except Exception as exc:  # noqa: BLE001
        st.error(
            f"Could not find Sleeper user '{username}'. "
            f"Check the username, or retry if Sleeper is unavailable. ({exc})")
        return

    if not all_leagues:
        st.info("No leagues found for this user this season.")
        return

    for l in all_leagues:
        league_id = l['league_id']
        name = l.get('name') or league_id
        st.markdown(f"## {name}")
        _trade_suggestions_league_fragment(league_id, user_id, season, week)
        st.markdown(f"(League ID: {league_id})")


def main():
    username = st.text_input(
        "Sleeper username", key='username_input',
        on_change=lambda: st.query_params.update({'username': st.session_state.username_input}),
        value=st.query_params.get('username'))
    active_leagues = []
    active_drafts = False
    locked_league_id = st.query_params.get('league')
    if username or locked_league_id:
        season = int(get_sport_state('nfl')['league_season'])
        if locked_league_id:
            try:
                league = Data.get_league(int(locked_league_id)).get_league()
                if (league.get('status') == 'in_season'
                        and str(league.get('season')) == str(season)):
                    active_leagues = [locked_league_id]
            except Exception as exc:  # noqa: BLE001 - surface Sleeper lookup failures
                st.error(f"Could not load league '{locked_league_id}'. ({exc})")
        elif username:
            try:
                _, leagues = get_user_leagues(username, season)
                active_leagues = [league['league_id'] for league in leagues
                                  if league.get('status') == 'in_season']
            except Exception as exc:  # noqa: BLE001 - surface Sleeper lookup failures
                st.error(f"Could not load leagues for Sleeper user '{username}'. ({exc})")
        if username:
            try:
                _, drafts = get_user_drafts(username, season)
                active_drafts = any(draft.get('status') == 'drafting'
                                    for draft in drafts)
            except Exception as exc:  # noqa: BLE001 - surface Sleeper lookup failures
                st.error(f"Could not load drafts for Sleeper user '{username}'. ({exc})")

    mode_options = []
    if active_leagues:
        mode_options.append("Live Scores")
    if active_drafts:
        mode_options.append("Draft Assistant")
    if active_leagues and username:
        mode_options.append("Waiver Guide")
        mode_options.append("Trade Suggestions")

    if not mode_options:
        st.session_state.pop('app_mode', None)
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
        if not username and not locked_league_id:
            st.info("Enter your Sleeper username to find active drafts and leagues.")
        else:
            st.info("No active drafts or leagues found this season.")
        return

    remembered_mode = st.query_params.get('mode', mode_options[0])
    mode_default = remembered_mode if remembered_mode in mode_options else mode_options[0]
    if st.session_state.get('app_mode') not in mode_options:
        st.session_state.pop('app_mode', None)
    mode = st.segmented_control(
        "View", mode_options, default=mode_default, key="app_mode",
        on_change=lambda: st.query_params.update({'mode': st.session_state.app_mode or mode_options[0]}))
    if mode not in mode_options:
        mode = mode_default
    week_val = st.session_state.get('week', 1)
    if mode == "Draft Assistant":
        render_draft_assistant(username)
        return
    if mode == "Waiver Guide":
        render_waiver_guide(username, int(week_val))
        return
    if mode == "Trade Suggestions":
        render_trade_suggestions(username, int(week_val))
        return

    context = Context(active_leagues)

    st.number_input("Week", min_value=1, max_value=18,
                    key='week', value=context.week)

    for league in context.leagues:
        st.markdown(f"## {league.name}")
        for matchup in league.matchups(context):
            matchup.render()
        st.markdown(f"(League ID: {league.id})")

if __name__ == "__main__":
    main()
