import tests.mock
from streamlit_app import Positions


def test_eligible_positions():
    data = tests.mock.data()
    data.positions = ['QB', 'RB', 'RB', 'WR', 'WR',
                      'WR', 'TE', 'FLEX', 'SUPER_FLEX', 'DEF']
    positions = Positions(data)

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
