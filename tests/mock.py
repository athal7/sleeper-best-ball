from unittest.mock import Mock
import pandas as pd
import sleeper_wrapper as sleeper
from streamlit_app import Data, Context

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
