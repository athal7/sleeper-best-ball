from streamlit.testing.v1 import AppTest
import pandas as pd
from streamlit_app import Data

user = "athal7"
league = "Metro Master"
league_id = "1204265604316409856"

def _app():
    return AppTest.from_file("streamlit_app.py", default_timeout=10)

def _validate_user(at: AppTest):
    assert at.text_input[0].value == user
    assert user in at.query_params['username']
    assert league in at.markdown[2].value
    assert len(at.table) == 1
    assert user in at.table[0].value


def _validate_league(at: AppTest):
    assert league in at.markdown[2].value
    assert len(at.table) > 1
    i = 0
    while at.table[i].value is not None and user not in at.table[i].value:
        i += 1
    assert user in at.table[i].value


def test_by_username_input():
    at = _app().run()
    at.text_input[0].set_value(user).run()
    _validate_user(at)


def test_by_username_query_param():
    at = _app()
    at.query_params['username'] = user
    at.run()
    _validate_user(at)


def test_by_league_query_param():
    at = _app()
    at.query_params['league'] = league_id
    at.run()
    _validate_league(at)


def test_from_user_to_league_to_user():
    at = _app().run()
    at.text_input[0].set_value(user).run()

    try:
        _validate_league(at)
        assert False, "_validate_league should have failed"
    except AssertionError:
        pass  

    at.button[0].click().run()
    _validate_league(at)
    assert league_id in at.query_params['league']

    at.button[0].click().run()
    _validate_user(at)
    assert 'league' not in at.query_params
    try:
        _validate_league(at)
        assert False, "_validate_league should have failed"
    except AssertionError:
        pass  
    

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
    assert p3.pos == 'TE'
    assert p3.team == 'C'
    assert p3.points == 20
    assert p3.fantasy_team == 'Team 1'
    assert p3.matchup_id == 1
    assert p3.pct_played == 1.0
    
    p2 = df.iloc[1]
    assert p2.name == 2
    assert p2.first_name == 'Player'
    assert p2.last_name == 'Two'
    assert p2.pos == 'WR'
    assert p2.team == 'B'
    assert round(p2.points, 2) == round((10 + (50*0.1 + 1*6) * 2/3), 2)
    assert p2.fantasy_team == 'Team 1'
    assert p2.matchup_id == 1
    assert p2.pct_played == 1/3

    p1 = df.iloc[2]
    assert p1.name == 1
    assert p1.first_name == 'Player'
    assert p1.last_name == 'One'
    assert p1.pos == 'QB'
    assert p1.team == 'A'
    assert round(p1.points, 2) == round((100*0.04 + 1*4), 2)
    assert p1.fantasy_team == 'Team 1'
    assert p1.matchup_id == 1
    assert p1.pct_played == 0

    p4 = df.iloc[3]
    assert p4.name == 4
    assert p4.first_name == 'Player'
    assert p4.last_name == 'Four'
    assert p4.pos == 'RB'
    assert p4.team == 'D'
    assert round(p4.points, 2) == round(0, 2)
    assert p4.fantasy_team == 'Team 1'
    assert p4.matchup_id == 1
    assert p4.pct_played == 0


def test_starting_positions():
    data = Data()
    data._positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE', 'FLEX', 'SUPER_FLEX', 'DEF']
    positions = data.starting_positions()
    print(positions)
    assert positions.loc['QB']['eligible'] == ['QB']
    assert positions.loc['RB']['eligible'] == ['RB']
    assert positions.loc['RB2']['eligible'] == ['RB']
    assert positions.loc['WR']['eligible'] == ['WR']
    assert positions.loc['WR2']['eligible'] == ['WR']
    assert positions.loc['WR3']['eligible'] == ['WR']
    assert positions.loc['TE']['eligible'] == ['TE']
    assert positions.loc['FX']['eligible'] == ['RB', 'WR', 'TE']
    assert positions.loc['SFX']['eligible'] == ['QB', 'RB', 'WR', 'TE']
    assert positions.loc['DEF']['eligible'] == ['DEF']