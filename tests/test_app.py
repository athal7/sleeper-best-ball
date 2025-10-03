from streamlit.testing.v1 import AppTest

user = "athal7"
league = "Metro Master"
league_id = "1204265604316409856"


def _validate_user(at: AppTest):
    assert at.text_input[0].value == user
    assert user in at.query_params['username']
    assert league in at.markdown[2].value
    assert len(at.dataframe) == 1
    assert user in at.dataframe[0].value


def _validate_league(at: AppTest):
    assert league in at.markdown[2].value
    assert len(at.dataframe) > 1
    i = 0
    while at.dataframe[i].value is not None and user not in at.dataframe[i].value:
        i += 1
    assert user in at.dataframe[i].value


def test_by_username_input():
    at = AppTest.from_file("app.py").run()
    at.text_input[0].set_value(user).run()
    _validate_user(at)


def test_by_username_query_param():
    at = AppTest.from_file("app.py")
    at.query_params['username'] = user
    at.run()
    _validate_user(at)


def test_by_league_query_param():
    at = AppTest.from_file("app.py")
    at.query_params['league'] = league_id
    at.run()
    _validate_league(at)


def test_from_user_to_league_to_user():
    at = AppTest.from_file("app.py").run()
    at.text_input[0].set_value(user).run()

    try:
        _validate_league(at)
        assert False, "_validate_league should have failed"
    except AssertionError:
        pass  

    at.button[0].click().run()
    _validate_league(at)
    assert league_id in at.query_params['league']

    at.button[0].click().run()
    _validate_user(at)
    assert 'league' not in at.query_params
    try:
        _validate_league(at)
        assert False, "_validate_league should have failed"
    except AssertionError:
        pass  