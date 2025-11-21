import pandas as pd
from streamlit_app import FantasyTeam


def test_fantasy_team_points_calculations():
    players_df = pd.DataFrame.from_dict({
        1: {'points': 10, 'optimistic': 15, 'position': 'QB'},
        2: {'points': 20, 'optimistic': 25, 'position': 'RB'},
        3: {'points': 30, 'optimistic': 35, 'position': 'WR'},
        4: {'points': 5, 'optimistic': 10, 'position': 'QB'},
    }, orient='index')
    positions_df = pd.DataFrame.from_dict({
        'QB': {'eligible': ['QB']},
        'RB': {'eligible': ['RB']},
        'WR': {'eligible': ['WR']},
    }, orient='index')
    team = FantasyTeam(
        name='Test Team', 
        players=[1,2,3],
        all_players=players_df,
        username='test_user',
        avatar='123456',
        matchup_id=1,
        record='2-1',
        rank=5,
        positions=positions_df
    )

    assert team.points == "60.00"
    assert team.projection == "75.00"