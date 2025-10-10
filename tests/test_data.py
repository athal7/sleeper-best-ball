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
        'B': {'status.period': 2, 'status.clock': 10*60},
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

    p3 = df.iloc[0]
    assert p3.name == 3
    assert p3.first_name == 'Player'
    assert p3.last_name == 'Three'
    assert p3.position == 'TE'
    assert p3.team == 'C'
    assert p3.points == 20
    assert p3.fantasy_team == 'Team 1'
    assert p3.matchup_id == 1
    assert p3.projected == False
    
    p2 = df.iloc[1]
    assert p2.name == 2
    assert p2.first_name == 'Player'
    assert p2.last_name == 'Two'
    assert p2.position == 'WR'
    assert p2.team == 'B'
    assert round(p2.points, 2) == round((10 + (50*0.1 + 1*6) * 2/3), 2)
    assert p2.fantasy_team == 'Team 1'
    assert p2.matchup_id == 1
    assert p2.projected == True

    p1 = df.iloc[2]
    assert p1.name == 1
    assert p1.first_name == 'Player'
    assert p1.last_name == 'One'
    assert p1.position == 'QB'
    assert p1.team == 'A'
    assert round(p1.points, 2) == round((100*0.04 + 1*4), 2)
    assert p1.fantasy_team == 'Team 1'
    assert p1.matchup_id == 1
    assert p1.projected == True

    p4 = df.iloc[3]
    assert p4.name == 4
    assert p4.first_name == 'Player'
    assert p4.last_name == 'Four'
    assert p4.position == 'RB'
    assert p4.team == 'D'
    assert round(p4.points, 2) == round(0, 2)
    assert p4.fantasy_team == 'Team 1'
    assert p4.matchup_id == 1
    assert p4.projected == False


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