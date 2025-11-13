import pandas as pd
from streamlit_app import League, Data

def stub_data() -> Data:
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

def test_points_calculations():
    data = stub_data()
    data.players = pd.DataFrame.from_dict({
        1: {'first_name': 'Player', 'last_name': 'One', 'team': 'A', 'position': 'QB', 'injury_status': None},
        2: {'first_name': 'Player', 'last_name': 'Two', 'team': 'B', 'position': 'WR', 'injury_status': None},
        3: {'first_name': 'Player', 'last_name': 'Three', 'team': 'C', 'position': 'TE', 'injury_status': None},
        4: {'first_name': 'Player', 'last_name': 'Four', 'team': 'D', 'position': 'RB', 'injury_status': None},
        5: {'first_name': 'Player', 'last_name': 'Five', 'team': 'C', 'position': 'K', 'injury_status': "Out"}
    }, orient='index')
    data.game_statuses = pd.DataFrame.from_dict({
        'A': {'quarter': 1, 'clock': 15*60, 'game_status': 'In Progress'},
        'B': {'quarter': 2, 'clock': 10*60, 'game_status': 'In Progress'},
        'C': {'quarter': 4, 'clock': 0, 'game_status': 'Final'}
    }, orient='index')
    data.projections = pd.DataFrame({
        1: {'passing_yards': 100, 'passing_touchdowns': 1},
        2: {'receiving_yards': 50, 'receiving_touchdowns': 1},
        3: {'receiving_yards': 75, 'receiving_touchdowns': 1}})
    data.stats = pd.DataFrame({
        2: {'receiving_yards': 10, 'receiving_touchdowns': 0},
        3: {'receiving_yards': 20, 'receiving_touchdowns': 0}})
    data.scoring = {
        'passing_yards': 0.04,
        'passing_touchdowns': 4,
        'receiving_yards': 0.1,
        'receiving_touchdowns': 6}
    data.positions = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'DEF']
    league = League(id=data.league_id, data=data)
    df = league.players()
    print(df)
    
    p1, p2, p3, p4, p5 = df.to_dict(orient='records')
    assert p1['points'] == 0
    assert round(p1['projection'], 2) == round((100*0.04 + 1*4), 2)
    assert p1['optimistic'] == p1['projection']

    assert round(p2['points'], 2) == round(10*0.1, 2)
    assert round(p2['projection'], 2) == round((50*0.1 + 1*6), 2)
    assert round(p2['optimistic'], 2) == round(
        p2['points'] + (2/3)*p2['projection'], 2)

    assert round(p3['points']) == round(20*0.1, 2)
    assert round(p3['projection'], 2) == round((75*0.1 + 1*6), 2)
    assert p3['optimistic'] == p3['points']

    assert p4['points'] == 0
    assert p4['projection'] == 0
    assert p4['optimistic'] == 0

    assert p5['points'] == 0
    assert p5['projection'] == 0
    assert p5['optimistic'] == 0


def test_starting_positions():
    data = stub_data()
    data.positions = ['QB', 'RB', 'RB', 'WR', 'WR',
                      'WR', 'TE', 'FLEX', 'SUPER_FLEX', 'DEF']
    league = League(id=data.league_id, data=data)

    positions = league.starting_positions()
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
