from streamlit.testing.v1 import AppTest

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