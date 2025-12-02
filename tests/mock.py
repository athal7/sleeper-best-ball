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