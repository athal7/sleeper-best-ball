from streamlit.testing.v1 import AppTest


def test_draft_assistant_mode_renders_prompt():
    at = AppTest.from_file("../streamlit_app.py", default_timeout=10).run()
    at.sidebar.radio[0].set_value("Draft Assistant").run()
    assert not at.exception
    assert any("Enter your Sleeper username" in m.value for m in at.info)
    assert any("Draft Recommendation Engine" in t.value for t in at.title)
