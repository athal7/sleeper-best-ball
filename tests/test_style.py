from streamlit_app import Style

def test_set_and_fetch():
    style = Style({
        'table': {
            'color': 'red',
            'font-size': '12px'
        }
    })
    assert style.table == "color: red; font-size: 12px"

def test_get_with_extra():
    style = Style({
        'button': {
            'color': 'blue',
        }
    })
    assert style.get('button', font_weight='bold') == "color: blue; font-weight: bold"