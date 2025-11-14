import pandas as pd
from streamlit_app import Data

def data() -> Data:
    return Data(
        league_id=123,
        game_statuses=pd.DataFrame(),
        matchups=pd.DataFrame(),
        rosters=pd.DataFrame(),
        players=pd.DataFrame(),
        projections=pd.DataFrame(),
        stats=pd.DataFrame(),
        scoring={},
        positions=[],
    )
