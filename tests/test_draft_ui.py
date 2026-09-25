from streamlit.testing.v1 import AppTest


def test_draft_assistant_mode_does_not_bypass_active_draft_requirement():
    at = AppTest.from_file("../streamlit_app.py", default_timeout=10)
    at.query_params['mode'] = "Draft Assistant"
    at.run()
    assert not at.exception
    assert any("Enter your Sleeper username" in m.value for m in at.info)
    assert not any("Draft Recommendation Engine" in t.value for t in at.title)
    assert not at.get('button_group')


def test_render_draft_assistant_renders_multiple_drafts(monkeypatch):
    import streamlit_app

    mock_drafts = [
        {'draft_id': 'd1', 'metadata': {'name': 'Draft One'}},
        {'draft_id': 'd2', 'metadata': {'name': 'Draft Two'}},
    ]
    monkeypatch.setattr(
        streamlit_app,
        'get_user_drafts',
        lambda username, season: ('user_1', mock_drafts),
    )
    rendered_fragments = []
    monkeypatch.setattr(
        streamlit_app,
        '_draft_assistant_fragment',
        lambda draft_id, user_id: rendered_fragments.append((draft_id, user_id)),
    )

    markdown_calls = []
    monkeypatch.setattr(streamlit_app.st, 'markdown', lambda text: markdown_calls.append(text))
    monkeypatch.setattr(streamlit_app.st, 'title', lambda title: None)

    streamlit_app.render_draft_assistant('test_user')

    assert rendered_fragments == [('d1', 'user_1'), ('d2', 'user_1')]
    assert '## Draft One' in markdown_calls
    assert '## Draft Two' in markdown_calls
