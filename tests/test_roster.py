import pytest
import pandas as pd
from streamlit_app import Roster


def build_roster(players_data: list[tuple[str, int, int]], positions_data: list[tuple[str, list[str]]]) -> Roster:
    players_df = pd.DataFrame([
        {'position': p[0], 'points': p[1], 'optimistic': p[2]} for p in players_data
    ])
    positions_df = pd.DataFrame.from_dict({
        pos: {'eligible': eligible} for pos, eligible in positions_data
    }, orient='index')
    return Roster(players=players_df, positions=positions_df)


@pytest.mark.parametrize("roster,expected", [
    (build_roster([('QB', 10, 10)], [('QB', ['QB'])]), ['QB']),
    (build_roster(
        [('WR', 9, 11), ('WR', 8, 12)],
        [('WR1', ['WR']), ('WR2', ['WR'])]
    ), ['WR1', 'WR2']),
    (build_roster(
        [('WR', 7, 11), ('WR', 8, 12)],
        [('WR', ['WR']), ('BN', ['WR'])]
    ), ['BN', 'WR']),
    (build_roster(
        [('RB', 7, 11), ('RB', 9, 10), ('WR', 8, 12), ('WR', 6, 9)],
        [('RB', ['RB']), ('WR', ['WR']),
         ('FLEX', ['RB', 'WR']), ('BN', ['RB', 'WR'])]
    ), ['FLEX', 'RB', 'WR', 'BN']),
])
def test_current_position_assignment(roster, expected):
    print(roster)
    assert roster.sort_index()['current_position'].tolist() == expected


@pytest.mark.parametrize("roster,expected", [
    (build_roster([('QB', 10, 10)], [('QB', ['QB'])]), ['QB']),
    (build_roster(
        [('WR', 9, 11), ('WR', 8, 12)],
        [('WR1', ['WR']), ('WR2', ['WR'])]
    ), ['WR2', 'WR1']),
    (build_roster(
        [('WR', 7, 11), ('WR', 8, 12)],
        [('WR', ['WR']), ('BN', ['WR'])]
    ), ['BN', 'WR']),
    (build_roster(
        [('RB', 7, 11), ('RB', 9, 10), ('WR', 8, 12), ('WR', 6, 9)],
        [('RB', ['RB']), ('WR', ['WR']),
         ('FLEX', ['RB', 'WR']), ('BN', ['RB', 'WR'])]
    ), ['RB', 'FLEX', 'WR', 'BN']),
])
def test_optimal_position_assignment(roster, expected):
    assert roster.sort_index()['spos'].tolist() == expected
