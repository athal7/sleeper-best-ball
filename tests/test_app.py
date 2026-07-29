from streamlit.testing.v1 import AppTest

user = "athal7"
league = "Metro Master"
league_id = "1312060096066355200"


def _app():
    return AppTest.from_file("streamlit_app.py", default_timeout=10)


def test_by_username_input():
    at = _app().run()
    at.text_input[0].set_value(user).run()
    assert any(league in m.value for m in at.markdown)
    assert any(league_id in m.value for m in at.markdown)


def test_by_username_query_param():
    at = _app()
    at.query_params['username'] = user
    at.run()
    assert any(league in m.value for m in at.markdown)
    assert any(league_id in m.value for m in at.markdown)


def test_by_league_query_param():
    at = _app()
    at.query_params['league'] = league_id
    at.run()
    assert any(league in m.value for m in at.markdown)
    assert any(league_id in m.value for m in at.markdown)