import pandas as pd
from data import Data


def test_rosters():
    data = Data()
    data._matchups = pd.DataFrame([{
        'players': [1, 2, 3, 4],
        'players_points': {1: 0, 2: 10, 3: 20, 4: None},
        'roster_id': 1,
        'matchup_id': 1
    }])
    data._rosters = pd.DataFrame([{
        'owner_id': 1,
        'roster_id': 1
    }]).set_index('roster_id')
    data._users = pd.DataFrame([{
        'user_id': 1,
        'display_name': 'Team 1'
    }]).set_index('user_id')
    data._players = pd.DataFrame.from_dict({
        1: {'first_name': 'Player', 'last_name': 'One', 'team': 'A', 'position': 'QB'},
        2: {'first_name': 'Player', 'last_name': 'Two', 'team': 'B', 'position': 'WR'},
        3: {'first_name': 'Player', 'last_name': 'Three', 'team': 'C', 'position': 'TE'},   
        4: {'first_name': 'Player', 'last_name': 'Four', 'team': 'D', 'position': 'RB'}
    }, orient='index')
    data._game_statuses = pd.DataFrame.from_dict({
        'A': {'status.period': 1, 'status.clock': 15*60},
        'B': {'status.period': 2, 'status.clock': 0},
        'C': {'status.period': 4, 'status.clock': 0}
    }, orient='index')
    data._projections = pd.DataFrame.from_dict({
        1: {'passing_yards': 100, 'passing_touchdowns': 1},
        2: {'receiving_yards': 50, 'receiving_touchdowns': 1},
        3: {'receiving_yards': 75, 'receiving_touchdowns': 1}
    }, orient='index')
    data._scoring = {
        'passing_yards': 0.04,
        'passing_touchdowns': 4,
        'receiving_yards': 0.1,
        'receiving_touchdowns': 6
    }
    data._positions = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'DEF']
    df = data.rosters()
    assert len(df) == 4
    assert df.iloc[0].name == 3
    assert df.iloc[0].to_dict() == {
        'first_name': 'Player',
        'last_name': 'Three',
        'position': 'TE',
        'team': 'C',
        'points': 20,
        'fantasy_team': 'Team 1',
        'matchup_id': 1,
        'projected': False
    }
    assert df.iloc[1].name == 2
    assert df.iloc[1].to_dict() == {
        'first_name': 'Player',
        'last_name': 'Two',
        'position': 'WR',
        'team': 'B',
        'points': 10 + .5 * (50*0.1 + 1*6), # 18.0
        'fantasy_team': 'Team 1',
        'matchup_id': 1,
        'projected': True
    }
    assert df.iloc[2].name == 1
    assert df.iloc[2].to_dict() == {
        'first_name': 'Player',
        'last_name': 'One',
        'position': 'QB',
        'team': 'A',
        'points': 100*0.04 + 1*4, # 8.0
        'fantasy_team': 'Team 1',
        'matchup_id': 1,
        'projected': True
    }
    assert df.iloc[3].name == 4
    assert df.iloc[3].to_dict() == {
        'first_name': 'Player',
        'last_name': 'Four',
        'position': 'RB',
        'team': 'D',
        'points': 0,
        'fantasy_team': 'Team 1',
        'matchup_id': 1,
        'projected': False
    }


def test_starting_positions():
    data = Data()
    data._positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'SUPER_FLEX', 'DEF']
    positions = data.starting_positions()
    assert positions.loc['QB1']['eligible'] == ['QB']
    assert positions.loc['RB1']['eligible'] == ['RB']
    assert positions.loc['RB2']['eligible'] == ['RB']
    assert positions.loc['WR1']['eligible'] == ['WR']
    assert positions.loc['WR2']['eligible'] == ['WR']
    assert positions.loc['TE1']['eligible'] == ['TE']
    assert positions.loc['FLEX1']['eligible'] == ['RB', 'WR', 'TE']
    assert positions.loc['SFLEX1']['eligible'] == ['QB', 'RB', 'WR', 'TE']
    assert positions.loc['DEF1']['eligible'] == ['DEF']