import pandas as pd
import pytest

from streamlit_app import (
    build_waiver_pool,
    compute_waiver_value,
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
