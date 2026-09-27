import pandas as pd

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


def test_trade_suggestions_mode_query_param_does_not_bypass_active_league_requirement():
    at = _app()
    at.query_params['mode'] = "Trade Suggestions"
    at.run()
    assert not at.exception
    assert any("Enter your Sleeper username" in m.value for m in at.info)
    assert not at.get('button_group')


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


def test_waiver_and_trade_fragments_share_raw_projections_and_use_league_scoring(monkeypatch):
    import streamlit_app as app

    players = pd.DataFrame.from_dict({
        'wr1': {'position': 'WR', 'first_name': 'One', 'last_name': 'Receiver', 'team': 'A'},
        'wr2': {'position': 'WR', 'first_name': 'Two', 'last_name': 'Receiver', 'team': 'B'},
        'rb1': {'position': 'RB', 'first_name': 'One', 'last_name': 'Runner', 'team': 'C'},
        'rb2': {'position': 'RB', 'first_name': 'Two', 'last_name': 'Runner', 'team': 'D'},
        'rb_fa': {'position': 'RB', 'first_name': 'Free', 'last_name': 'Agent', 'team': 'E'},
    }, orient='index')
    rosters = pd.DataFrame({
        'owner_id': ['u1', 'u2'],
        'players': [['wr1', 'wr2'], ['rb1', 'rb2']],
    }, index=[1, 2])
    calls = []

    class FakeStats:
        def get_week_projections(self, phase, season, week):
            calls.append((season, week))
            if week != 1:
                return {}
            return {
                'wr1': {'rec_yd': 200, 'adp_dd_ppr': 10},
                'wr2': {'rec_yd': 180, 'adp_dd_ppr': 20},
                'rb1': {'rush_yd': 200, 'adp_dd_ppr': 30},
                'rb2': {'rush_yd': 180, 'adp_dd_ppr': 40},
                'rb_fa': {'rush_yd': 300, 'adp_dd_ppr': 50},
            }

    league_fetches = []

    class FakeLeague:
        def __init__(self, league_id):
            league_fetches.append(league_id)
            self.league_id = league_id

        def get_league(self):
            return {'settings': {'teams': 2, 'slots_rb': 1, 'slots_wr': 1}}

        def get_rosters(self):
            return [{'roster_id': rid, **row.to_dict()} for rid, row in rosters.iterrows()]

        def get_users(self):
            return [{'user_id': 'u1'}, {'user_id': 'u2'}]

        def get_transactions(self, week):
            return []

    league_cache = {}

    def get_cached_league(league_id):
        if league_id not in league_cache:
            league_cache[league_id] = FakeLeague(league_id)
        return league_cache[league_id]

    monkeypatch.setattr(app.sleeper, 'Stats', FakeStats)
    monkeypatch.setattr(app.sleeper, 'League', FakeLeague)
    monkeypatch.setattr(app, '_projection_cache_hour', lambda: 1234)
    monkeypatch.setattr(app.Data, 'get_league', staticmethod(get_cached_league))
    monkeypatch.setattr(app.Data, 'get_players', staticmethod(lambda: players))
    monkeypatch.setattr(app.Data, 'get_rosters', staticmethod(
        lambda league_id: pd.DataFrame({'name': ['User', 'Partner']}, index=[1, 2])))
    monkeypatch.setattr(app.Data, 'get_bye_weeks', staticmethod(lambda season: {}))
    monkeypatch.setattr(app, 'fetch_draft_scoring', lambda league_id: {
        'rec_yd': 0.1 if league_id == '101' else 0.2,
        'rush_yd': 0.1 if league_id == '101' else 0.2,
    })
    waiver_results = []
    trade_results = []
    monkeypatch.setattr(app, 'render_waiver_pool', waiver_results.append)
    monkeypatch.setattr(app, 'render_trade_suggestions_table', trade_results.append)
    app.Data._cached_projections.clear()
    app._cached_season_projection_stats.clear()
    try:
        app._waiver_guide_league_fragment.__wrapped__('101', 'u1', 2031, 1)
        app._trade_suggestions_league_fragment('202', 'u1', 2031, 1)
        assert calls == [(2031, week) for week in app.SEASON_WEEKS]
        assert league_fetches == [101, 202]
        waiver = waiver_results[0].iloc[0]
        assert waiver['add_player_id'] == 'rb_fa'
        assert waiver['drop_player_id'] == 'wr2'
        assert waiver['uplift'] == 30.0
        trade = trade_results[0]
        swap = trade[(trade['give_player_id'] == 'wr2') &
                     (trade['receive_player_id'] == 'rb2')].iloc[0]
        assert swap['my_uplift'] == 36.0
        assert swap['partner_uplift'] == 36.0
    finally:
        app._cached_season_projection_stats.clear()
        app.Data._cached_projections.clear()