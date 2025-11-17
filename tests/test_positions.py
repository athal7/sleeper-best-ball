import tests.mock
from streamlit_app import Positions


def test_eligible_positions():
    data = tests.mock.data()
    data.league.get_league.return_value = {
        'roster_positions': ['QB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE', 'FLEX', 'SUPER_FLEX', 'DEF']
    }
    positions = Positions(data)

    assert positions.loc['QB1']['eligible'] == ['QB']
    assert positions.loc['RB1']['eligible'] == ['RB']
    assert positions.loc['RB2']['eligible'] == ['RB']
    assert positions.loc['WR1']['eligible'] == ['WR']
    assert positions.loc['WR2']['eligible'] == ['WR']
    assert positions.loc['WR3']['eligible'] == ['WR']
    assert positions.loc['TE1']['eligible'] == ['TE']
    assert positions.loc['FX1']['eligible'] == ['RB', 'WR', 'TE']
    assert positions.loc['SFX1']['eligible'] == ['QB', 'RB', 'WR', 'TE']
    assert positions.loc['DEF1']['eligible'] == ['DEF']
