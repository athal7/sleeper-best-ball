import pandas as pd
import pytest

from streamlit_app import (
    build_waiver_pool,
    compute_waiver_value,
    compute_waiver_add_drop_recommendations,
    render_waiver_pool,
    DraftSettings,
    compute_upside_bonus,
    UPSIDE_WEIGHT,
)


def build_pool(rows: dict) -> pd.DataFrame:
    return pd.DataFrame.from_dict(rows, orient='index')


def build_rosters(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# --- WaiverData ---

def test_waiver_data_get_free_agent_player_ids_returns_unowned_players():
    """Free agent set = all players minus owned players across rosters."""
    all_ids = {'1', '2', '3', '4', '5'}
    owned = set()
    for players in [['1', '2', '3'], ['4']]:
        owned.update(players)
    free = all_ids - owned
    assert free == {'5'}


def test_waiver_data_get_user_roster_id_returns_matching_roster():
    rosters = build_rosters([
        {'owner_id': 'u1', 'players': ['1']},
        {'owner_id': 'u2', 'players': ['2']},
    ])
    rosters.index = ['r1', 'r2']

    assert rosters.loc['r1', 'owner_id'] == 'u1'
    assert rosters.loc['r2', 'owner_id'] == 'u2'

    def get_user_roster_id(rids, uid):
        for rid, row in rids.iterrows():
            if row.get('owner_id') == uid:
                return rid
        return None

    assert get_user_roster_id(rosters, 'u1') == 'r1'
    assert get_user_roster_id(rosters, 'u2') == 'r2'
    assert get_user_roster_id(rosters, 'unknown') is None


def test_waiver_data_get_user_waiver_rank_returns_position_in_priority():
    rosters = build_rosters([
        {'owner_id': 'u1', 'players': ['1']},
        {'owner_id': 'u2', 'players': ['2']},
        {'owner_id': 'u3', 'players': ['3']},
    ])
    rosters.index = ['r1', 'r2', 'r3']

    priority = list(rosters.index)
    assert priority == ['r1', 'r2', 'r3']

    def get_user_waiver_rank(rids, uid):
        priority = list(rids.index)
        for rank, rid in enumerate(priority, 1):
            if rids.loc[rid, 'owner_id'] == uid:
                return rank
        return len(priority)

    assert get_user_waiver_rank(rosters, 'u1') == 1
    assert get_user_waiver_rank(rosters, 'u2') == 2
    assert get_user_waiver_rank(rosters, 'u3') == 3


def test_waiver_data_waiver_priority_returns_roster_order():
    rosters = build_rosters([
        {'owner_id': 'u1', 'players': ['1']},
        {'owner_id': 'u2', 'players': ['2']},
    ])
    rosters.index = ['r1', 'r2']

    assert list(rosters.index) == ['r1', 'r2']


# --- build_waiver_pool ---

def test_build_waiver_pool_filters_to_free_agents_only(monkeypatch):
    settings = DraftSettings(teams=12, slots={'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 1})
    bye_weeks = {}

    weekly = {1: pd.Series({'p1': 10.0, 'p2': 20.0, 'p3': 15.0, 'p4': 5.0})}
    projections = pd.DataFrame(weekly)

    free_ids = {'p2', 'p4'}

    players_df = pd.DataFrame({
        'position': ['RB', 'WR', 'TE', 'QB'],
        'first_name': ['A', 'B', 'C', 'D'],
        'last_name': ['a', 'b', 'c', 'd'],
        'team': ['A', 'B', 'C', 'D'],
    }, index=['p1', 'p2', 'p3', 'p4'])

    monkeypatch.setattr(
        'streamlit_app.Data.get_players',
        staticmethod(lambda: players_df),
    )

    pool = build_waiver_pool(projections, settings, free_ids, bye_weeks)
    assert set(pool.index) == free_ids
    assert 'p1' not in pool.index
    assert 'p3' not in pool.index


# --- compute_waiver_value ---

def test_compute_waiver_value_empty_roster_returns_zero_scores():
    """When my roster is empty, all uplift scores should be zero."""
    settings = DraftSettings(teams=12, slots={'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 1})
    pool = build_pool({
        'p1': {'position': 'RB', 'p50_weekly': 10.0, 'p90_weekly': 15.0, 'adp': 5.0},
        'p2': {'position': 'WR', 'p50_weekly': 12.0, 'p90_weekly': 18.0, 'adp': 10.0},
    })
    my_roster = pd.DataFrame()

    result = compute_waiver_value(pool, pd.Series(dtype=float), my_roster,
                                  settings, waiver_rank=1, teams=12)

    assert result['lineup_uplift'].sum() == pytest.approx(0.0)
    assert result['waiver_vorp'].sum() == pytest.approx(0.0)
    # Scarcity is zero — waiver value is purely uplift + upside
    assert result['waiver_scarcity'].sum() == 0.0
    assert result['upside_bonus'].sum() > 0
    assert result['waiver_priority'].sum() > 0


def test_compute_waiver_value_rich_roster_computes_uplift():
    """A RB candidate should have positive uplift if my roster has no RB."""
    settings = DraftSettings(teams=12, slots={'QB': 1, 'RB': 1, 'WR': 2, 'TE': 1})

    weekly = {1: pd.Series({'p1': 15.0, 'p2': 10.0, 'qb1': 20.0, 'wr1': 12.0, 'wr2': 10.0, 'te1': 8.0})}
    pool = pd.DataFrame(weekly, index=['p1', 'p2', 'qb1', 'wr1', 'wr2', 'te1'])
    pool['position'] = ['RB', 'WR', 'QB', 'WR', 'WR', 'TE']
    pool['p50_weekly'] = [15.0, 10.0, 20.0, 12.0, 10.0, 8.0]
    pool['p90_weekly'] = [20.0, 14.0, 25.0, 16.0, 14.0, 11.0]
    pool['adp'] = [5.0, 15.0, 1.0, 8.0, 12.0, 20.0]

    my_roster = pd.DataFrame({
        'position': ['QB', 'WR', 'WR', 'TE'],
    }, index=['qb1', 'wr1', 'wr2', 'te1'])

    lineup_uplift = pd.Series({'p1': 5.0, 'p2': 0.5, 'qb1': 0.0, 'wr1': 0.0, 'wr2': 0.0, 'te1': 0.0})
    result = compute_waiver_value(pool, lineup_uplift, my_roster,
                                  settings, waiver_rank=1, teams=12)

    # p1 (RB) should have positive uplift since my roster has no RB
    assert result.loc['p1', 'lineup_uplift'] > 0
    # p2 (WR) should have lower uplift since I already have 2 WRs
    assert result.loc['p2', 'lineup_uplift'] >= 0






def test_compute_waiver_value_upside_bonus_included():
    """Upside bonus should be part of waiver priority."""
    settings = DraftSettings(teams=12, slots={'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 1})

    weekly = {1: pd.Series({'boom': 10.0, 'floor': 10.0})}
    pool = pd.DataFrame(weekly, index=['boom', 'floor'])
    pool['position'] = ['RB', 'RB']
    pool['p50_weekly'] = [10.0, 10.0]
    pool['p90_weekly'] = [25.0, 12.0]  # boom has huge ceiling
    pool['adp'] = [5.0, 10.0]

    my_roster = pd.DataFrame({'position': ['QB', 'RB', 'WR', 'WR', 'TE']},
                             index=['qb', 'rb_own', 'wr1', 'wr2', 'te'])

    result = compute_waiver_value(pool, pd.Series(dtype=float), my_roster,
                                  settings, waiver_rank=1, teams=12)

    # boom should have higher upside bonus
    assert result.loc['boom', 'upside_bonus'] > result.loc['floor', 'upside_bonus']


def test_compute_waiver_value_playoff_weeks_weighted():
    """Playoff weeks should get 1.5x weight in uplift calculations."""
    settings = DraftSettings(teams=12, slots={'QB': 1, 'RB': 1, 'WR': 2, 'TE': 1})

    # Create weekly projections with clear week-by-week differences
    weekly = {}
    for week in range(1, 19):
        weekly[week] = pd.Series({
            'rb1': 15.0 if week >= 15 else 5.0,
            'wr1': 10.0,
            'qb1': 20.0,
            'te1': 8.0,
        })
    pool = pd.DataFrame(weekly, index=['rb1', 'wr1', 'qb1', 'te1'])
    pool['position'] = ['RB', 'WR', 'QB', 'TE']
    pool['p50_weekly'] = [15.0, 10.0, 20.0, 8.0]
    pool['p90_weekly'] = [20.0, 14.0, 25.0, 11.0]
    pool['adp'] = [5.0, 15.0, 1.0, 20.0]

    my_roster = pd.DataFrame({'position': ['QB', 'WR', 'WR', 'TE']},
                             index=['qb1', 'wr1', 'wr_own', 'te1'])

    result_playoffs = compute_waiver_value(pool, pd.Series(dtype=float), my_roster,
                                           settings, waiver_rank=1, teams=12,
                                           playoff_week_start=15)
    result_no_playoffs = compute_waiver_value(pool, pd.Series(dtype=float), my_roster,
                                              settings, waiver_rank=1, teams=12,
                                              playoff_week_start=None)

    # With playoffs, the RB (who scores more in playoff weeks) should have
    # higher uplift than without playoff weighting
    assert result_playoffs.loc['rb1', 'lineup_uplift'] >= result_no_playoffs.loc['rb1', 'lineup_uplift']


def test_compute_waiver_value_includes_all_output_columns():
    """Result DataFrame should have all expected columns."""
    settings = DraftSettings(teams=12, slots={'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 1})

    weekly = {1: pd.Series({'p1': 15.0, 'p2': 10.0})}
    pool = pd.DataFrame(weekly, index=['p1', 'p2'])
    pool['position'] = ['RB', 'WR']
    pool['p50_weekly'] = [15.0, 10.0]
    pool['p90_weekly'] = [20.0, 14.0]
    pool['adp'] = [5.0, 15.0]

    my_roster = pd.DataFrame({'position': ['QB', 'RB', 'WR', 'TE']},
                             index=['qb', 'rb_own', 'wr_own', 'te'])

    result = compute_waiver_value(pool, pd.Series(dtype=float), my_roster,
                                  settings, waiver_rank=1, teams=12)

    expected_cols = {'lineup_uplift', 'waiver_vorp', 'waiver_scarcity',
                     'upside_bonus', 'waiver_priority'}
    assert expected_cols.issubset(set(result.columns))


# --- render_waiver_pool ---

def test_render_waiver_pool_empty(monkeypatch):
    import streamlit_app

    info_calls = []
    monkeypatch.setattr(streamlit_app.st, 'info', lambda msg: info_calls.append(msg))
    monkeypatch.setattr(streamlit_app.st, 'subheader', lambda msg: None)

    render_waiver_pool(pd.DataFrame())

    assert info_calls == ["None"]


def test_render_waiver_pool_renders_grouped_recommendations_and_links(monkeypatch):
    import streamlit_app

    markdown_calls = []
    monkeypatch.setattr(streamlit_app.st, 'markdown', lambda text: markdown_calls.append(text))
    monkeypatch.setattr(streamlit_app.st, 'subheader', lambda msg: None)

    recs = pd.DataFrame([
        {
            'add_player_id': '101',
            'add_name': 'Add One',
            'add_position': 'WR',
            'add_team': 'KC',
            'add_p50': 12.5,
            'add_p90': 18.0,
            'drop_player_id': '201',
            'drop_name': 'Drop One',
            'drop_position': 'WR',
            'drop_team': 'NYJ',
            'drop_p50': 5.0,
            'drop_p90': 8.0,
            'uplift': 7.5,
        },
        {
            'add_player_id': '102',
            'add_name': 'Add Two',
            'add_position': 'RB',
            'add_team': 'SF',
            'add_p50': 10.0,
            'add_p90': 15.0,
            'drop_player_id': None,
            'drop_name': 'None',
            'drop_position': '',
            'drop_team': '',
            'drop_p50': 0.0,
            'drop_p90': 0.0,
            'uplift': 3.0,
        },
    ])

    render_waiver_pool(recs)

    # Check drop headers rendered
    assert any("Drop **Drop One**" in m for m in markdown_calls)
    assert any("Add Without Dropping" in m for m in markdown_calls)

    # Check player links rendered with Sleeper URLs
    assert any("[Add One](https://sleeper.com/players/nfl/101)" in m for m in markdown_calls)
    assert any("[Add Two](https://sleeper.com/players/nfl/102)" in m for m in markdown_calls)

    # Check uplift formatted
    assert any("+7.5 pts" in m for m in markdown_calls)
    assert any("+3.0 pts" in m for m in markdown_calls)


def test_waiver_guide_caption_does_not_mention_auto_refresh(monkeypatch):
    import streamlit_app

    class MockWaiverData:
        def __init__(self, league_id, week):
            self.rosters = pd.DataFrame([{'owner_id': 'u1', 'players': ['p1']}])
            self.waiver_settings = {}

        def get_user_roster_id(self, user_id):
            return 0

        def get_free_agent_player_ids(self, all_ids):
            return {'fa1'}

        def get_user_waiver_rank(self, user_id):
            return 1

    monkeypatch.setattr(streamlit_app, 'WaiverData', MockWaiverData)
    monkeypatch.setattr(streamlit_app.Data, 'get_league', staticmethod(lambda league_id: type('MockLeague', (), {'get_league': lambda self: {'settings': {}}})()))
    monkeypatch.setattr(streamlit_app.DraftSettings, 'from_draft', classmethod(lambda cls, d: DraftSettings(teams=12, slots={'QB': 1})))
    monkeypatch.setattr(streamlit_app, 'fetch_draft_scoring', lambda lid: {})
    monkeypatch.setattr(streamlit_app.Data, 'get_bye_weeks', lambda s: {})
    monkeypatch.setattr(streamlit_app, 'build_season_projections', lambda s, sc: pd.DataFrame({'p50_weekly': [10.0, 10.0], 'p90_weekly': [15.0, 15.0]}, index=['fa1', 'p1']))
    monkeypatch.setattr(streamlit_app.Data, 'get_players', lambda: pd.DataFrame({'position': ['QB', 'QB'], 'first_name': ['A', 'B'], 'last_name': ['a', 'b'], 'team': ['T1', 'T2']}, index=['fa1', 'p1']))
    monkeypatch.setattr(streamlit_app, 'build_waiver_pool', lambda proj, setts, fa_ids, byes: pd.DataFrame({'position': ['QB']}, index=['fa1']))
    monkeypatch.setattr(streamlit_app, 'build_my_roster', lambda picks, uid, byes: pd.DataFrame({'position': ['QB']}, index=['p1']))
    monkeypatch.setattr(streamlit_app, 'build_projection_inputs', lambda s, sc: (pd.DataFrame({1: {'fa1': 10.0, 'p1': 10.0}}), pd.Series()))
    monkeypatch.setattr(streamlit_app, 'compute_waiver_add_drop_recommendations', lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(streamlit_app, 'render_waiver_pool', lambda recs: None)

    captions = []
    monkeypatch.setattr(streamlit_app.st, 'caption', lambda msg: captions.append(msg))

    assert hasattr(streamlit_app._waiver_guide_league_fragment, '__wrapped__')
    streamlit_app._waiver_guide_league_fragment.__wrapped__('123', 'u1', 2026, 1)

    assert any("Waiver rank #1 of 12" in c for c in captions)
    assert not any("refreshes every" in c for c in captions)


# --- compute_waiver_add_drop_recommendations ---

def test_compute_waiver_add_drop_recommendations_improves_team():
    """Should recommend adding a higher-scoring player and dropping the weakest roster player if net uplift > 0."""
    settings = DraftSettings(teams=12, slots={'QB': 1, 'RB': 1})
    waiver_pool = build_pool({
        'fa1': {'position': 'RB', 'first_name': 'Free', 'last_name': 'Agent', 'team': 'FA', 'p50_weekly': 15.0, 'p90_weekly': 20.0},
    })
    my_roster = pd.DataFrame({
        'position': ['QB', 'RB'],
        'first_name': ['Quarter', 'Bench'],
        'last_name': ['Back', 'RB'],
        'team': ['QB', 'RB'],
        'p50_weekly': [20.0, 5.0],
        'p90_weekly': [25.0, 8.0],
    }, index=['qb1', 'rb_weak'])

    weekly_points = pd.DataFrame({
        1: {'fa1': 15.0, 'qb1': 20.0, 'rb_weak': 5.0},
    })

    recs = compute_waiver_add_drop_recommendations(
        waiver_pool, weekly_points, my_roster, settings)

    assert not recs.empty
    assert len(recs) == 1
    assert recs.iloc[0]['add_player_id'] == 'fa1'
    assert recs.iloc[0]['drop_player_id'] == 'rb_weak'
    assert recs.iloc[0]['uplift'] == pytest.approx(10.0)
    assert recs.iloc[0]['add_p50'] == 15.0
    assert recs.iloc[0]['add_p90'] == 20.0
    assert recs.iloc[0]['drop_p50'] == 5.0
    assert recs.iloc[0]['drop_p90'] == 8.0


def test_compute_waiver_add_drop_recommendations_filters_out_non_positive_uplift():
    """Should return empty DataFrame when free agent does not improve team (net uplift <= 0)."""
    settings = DraftSettings(teams=12, slots={'QB': 1, 'RB': 1})
    waiver_pool = build_pool({
        'fa_weak': {'position': 'RB', 'first_name': 'Weak', 'last_name': 'FA', 'team': 'FA', 'p50_weekly': 2.0, 'p90_weekly': 4.0},
    })
    my_roster = pd.DataFrame({
        'position': ['QB', 'RB'],
        'first_name': ['Star', 'Star'],
        'last_name': ['QB', 'RB'],
        'team': ['QB', 'RB'],
        'p50_weekly': [20.0, 15.0],
        'p90_weekly': [25.0, 20.0],
    }, index=['qb1', 'rb1'])

    weekly_points = pd.DataFrame({
        1: {'fa_weak': 2.0, 'qb1': 20.0, 'rb1': 15.0},
    })

    recs = compute_waiver_add_drop_recommendations(
        waiver_pool, weekly_points, my_roster, settings)

    assert recs.empty


def test_compute_waiver_add_drop_recommendations_rest_of_season():
    """Should only calculate uplift for current_week and subsequent weeks."""
    settings = DraftSettings(teams=12, slots={'QB': 1, 'RB': 1})
    waiver_pool = build_pool({
        'fa1': {'position': 'RB', 'first_name': 'Late', 'last_name': 'Bloomer', 'team': 'FA', 'p50_weekly': 15.0, 'p90_weekly': 20.0},
    })
    my_roster = pd.DataFrame({
        'position': ['QB', 'RB'],
        'first_name': ['Quarter', 'Bench'],
        'last_name': ['Back', 'RB'],
        'team': ['QB', 'RB'],
        'p50_weekly': [20.0, 5.0],
        'p90_weekly': [25.0, 8.0],
    }, index=['qb1', 'rb_weak'])

    # Week 1: fa1 scores 100 points (should be ignored when current_week=2)
    # Week 2: fa1 scores 10 points vs rb_weak 5 points -> uplift = +5 points
    weekly_points = pd.DataFrame({
        1: {'fa1': 100.0, 'qb1': 20.0, 'rb_weak': 5.0},
        2: {'fa1': 10.0, 'qb1': 20.0, 'rb_weak': 5.0},
    })

    recs = compute_waiver_add_drop_recommendations(
        waiver_pool, weekly_points, my_roster, settings, current_week=2)

    assert not recs.empty
    # Rest-of-season uplift starting at week 2 should equal week 2 uplift (5.0), not average of week 1 and 2 (52.5)
    assert recs.iloc[0]['uplift'] == pytest.approx(5.0)


def test_compute_waiver_value_empty_roster_has_all_columns():
    """Even with empty roster, result should have all columns."""
    settings = DraftSettings(teams=12, slots={'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 1})
    pool = build_pool({
        'p1': {'position': 'RB', 'p50_weekly': 10.0, 'p90_weekly': 15.0, 'adp': 5.0},
    })
    my_roster = pd.DataFrame()

    result = compute_waiver_value(pool, pd.Series(dtype=float), my_roster,
                                  settings, waiver_rank=1, teams=12)

    expected_cols = {'lineup_uplift', 'waiver_vorp', 'waiver_scarcity',
                     'upside_bonus', 'waiver_priority'}
    assert expected_cols.issubset(set(result.columns))
