from streamlit.testing.v1 import AppTest
import pandas as pd
from streamlit_app import Data

user = "athal7"
league = "Metro Master"
league_id = "1204265604316409856"

def _app():
    return AppTest.from_file("streamlit_app.py", default_timeout=10)

def test_by_username_input():
    at = _app().run()
    at.text_input[0].set_value(user).run()
    assert league in at.markdown[0].value
    assert league_id in at.markdown[1].value


def test_by_username_query_param():
    at = _app()
    at.query_params['username'] = user
    at.run()
    assert league in at.markdown[0].value
    assert league_id in at.markdown[1].value


def test_by_league_query_param():
    at = _app()
    at.query_params['league'] = league_id
    at.run()
    assert league in at.markdown[0].value
    assert league_id in at.markdown[1].value


def test_players():
    data = Data()
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
    data._projections = {
        1: {'passing_yards': 100, 'passing_touchdowns': 1},
        2: {'receiving_yards': 50, 'receiving_touchdowns': 1},
        3: {'receiving_yards': 75, 'receiving_touchdowns': 1}
    }
    data._stats = {
        2: {'receiving_yards': 10, 'receiving_touchdowns': 0},
        3: {'receiving_yards': 20, 'receiving_touchdowns': 0}
    }
    data._scoring = {
        'passing_yards': 0.04,
        'passing_touchdowns': 4,
        'receiving_yards': 0.1,
        'receiving_touchdowns': 6
    }
    data._positions = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'DEF']
    df = data.players()
    print(df)
    assert len(df) == 4
    
    p1, p2, p3, p4 = df.to_dict(orient='records')
    assert p1['name'] == 'P. One'
    assert p1['position'] == 'QB'
    assert p1['team'] == 'A'
    assert p1['points'] == 0
    assert round(p1['projection'], 2) == round((100*0.04 + 1*4), 2)
    assert p1['optimistic'] == p1['projection']
    assert p1['pct_played'] == 0

    assert p2['name'] == 'P. Two'
    assert p2['position'] == 'WR'
    assert p2['team'] == 'B'
    assert round(p2['points'], 2) == round(10*0.1, 2)
    assert round(p2['projection'], 2) == round((50*0.1 + 1*6), 2)
    assert round(p2['optimistic'], 2) == round(p2['points'] + (2/3)*p2['projection'], 2)
    assert p2['pct_played'] == 1/3

    assert p3['name'] == 'P. Three'
    assert p3['position'] == 'TE'
    assert round(p3['points']) == round(20*0.1, 2)
    assert round(p3['projection'], 2) == round((75*0.1 + 1*6), 2)
    assert p3['optimistic'] == p3['points']
    assert p3['pct_played'] == 1

    assert p4['name'] == 'P. Four'
    assert p4['position'] == 'RB'
    assert p4['team'] == 'D'
    assert p4['points'] == 0
    assert p4['projection'] == 0
    assert p4['optimistic'] == 0
    assert p4['pct_played'] == 0


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