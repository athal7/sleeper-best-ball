from typing import cast
import pandas as pd
from streamlit_app import FantasyTeam, Positions


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


def test_unavailable_player_metadata_does_not_break_matchup_scores():
    players_df = pd.DataFrame.from_dict({
        'known': {'points': 8, 'optimistic': 12, 'position': 'QB'},
    }, orient='index')
    positions_df = pd.DataFrame.from_dict({
        'QB': {'eligible': ['QB']},
    }, orient='index')
    def make_team(ids: list[str]) -> FantasyTeam:
        return FantasyTeam(
            players=pd.Series(ids), all_players=players_df,
            positions=cast(Positions, positions_df), name='Test Team',
            username='test_user', avatar='', matchup_id='1',
            record='0-0', rank=1,
        )

    mixed = make_team(['missing', 'known'])
    assert mixed.roster.index.tolist() == ['known']
    assert mixed.points == '8.00'
    assert mixed.projection == '12.00'

    unavailable = make_team(['missing'])
    assert unavailable.roster.empty
    assert unavailable.points == '0.00'
    assert unavailable.projection == '0.00'