from dataclasses import asdict
from unittest.mock import Mock
import pandas as pd
import sleeper_wrapper as sleeper
from streamlit_app import Data, Context, Player

def data() -> Data:
    return Data(
        league_id=123,
        context=Mock(Context),
        game_statuses=pd.DataFrame(),
        matchups=pd.DataFrame(),
        rosters=pd.DataFrame(),
        players=pd.DataFrame(),
        projections=pd.DataFrame(),
        stats=pd.DataFrame(),
        league=Mock(sleeper.League)
    )

def game_status(**kwargs) -> dict:
    m = {
        'quarter': 1,
        'clock': 15*60,
        'game_status': 'Upcoming',
        'home': True,
        'opponent': 'XYZ',
        'score': None,
        'opponent_score': None,
        'game_time': '2024-09-01T13:00:00Z'
    }
    m.update(kwargs)
    return m

def player(**kwargs) -> dict:
    m = asdict(Player())
    m.update(kwargs)
    return m

def draft(**kwargs) -> dict:
    m = {
        'type': 'snake',
        'status': 'drafting',
        'draft_id': '999',
        'league_id': '123',
        'settings': {
            'teams': 12,
            'slots_qb': 1,
            'slots_rb': 2,
            'slots_wr': 3,
            'slots_te': 1,
            'slots_flex': 1,
            'slots_super_flex': 1,
            'slots_k': 0,
            'slots_def': 0,
            'slots_bn': 15,
        },
        'draft_order': {'u1': 1, 'u2': 2},
    }
    m.update(kwargs)
    return m

def pick(**kwargs) -> dict:
    m = {
        'player_id': '1',
        'picked_by': 'u1',
        'roster_id': '1',
        'round': 1,
        'draft_slot': 1,
        'pick_no': 1,
        'metadata': {},
        'is_keeper': None,
        'draft_id': '999',
    }
    m.update(kwargs)
    return m