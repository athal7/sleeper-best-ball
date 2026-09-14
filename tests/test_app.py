from streamlit.testing.v1 import AppTest

user = "athal7"
league = "Metro Master"
league_id = "1312060096066355200"


def _app():
    return AppTest.from_file("../streamlit_app.py", default_timeout=30)


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


def test_render_waiver_guide_renders_multiple_leagues(monkeypatch):
    import streamlit_app

    mock_leagues = [
        {'league_id': 'l1', 'name': 'League One'},
        {'league_id': 'l2', 'name': 'League Two'},
    ]
    monkeypatch.setattr(
        streamlit_app,
        'get_user_leagues',
        lambda username, season: ('user_1', mock_leagues),
    )
    rendered_fragments = []
    monkeypatch.setattr(
        streamlit_app,
        '_waiver_guide_league_fragment',
        lambda league_id, user_id, season, week: rendered_fragments.append((league_id, user_id, week)),
    )

    markdown_calls = []
    monkeypatch.setattr(streamlit_app.st, 'markdown', lambda text: markdown_calls.append(text))
    monkeypatch.setattr(streamlit_app.st, 'title', lambda title: None)

    streamlit_app.render_waiver_guide('test_user', 1)

    assert rendered_fragments == [('l1', 'user_1', 1), ('l2', 'user_1', 1)]
    assert '## League One' in markdown_calls
    assert '## League Two' in markdown_calls


def test_by_league_query_param():
    at = _app()
    at.query_params['league'] = league_id
    at.run()
    assert any(league in m.value for m in at.markdown)
    assert any(league_id in m.value for m in at.markdown)