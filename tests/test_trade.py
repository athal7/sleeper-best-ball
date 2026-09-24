import pandas as pd
import pytest

from streamlit_app import (
    compute_trade_recommendations,
    DraftSettings,
    render_trade_suggestions,
)


def build_pool(rows: dict) -> pd.DataFrame:
    return pd.DataFrame.from_dict(rows, orient='index')


def test_compute_trade_recommendations_win_win_trade():
    """Win-win trade: My Team has excess WR and needs RB, Partner Team has excess RB and needs WR.
    Trading My extra WR for Partner's extra RB improves both teams' lineups."""
    settings = DraftSettings(teams=12, slots={'RB': 1, 'WR': 1})

    # My Team: 2 WRs (20, 18), 0 RBs
    my_roster = pd.DataFrame({
        'position': ['WR', 'WR'],
        'first_name': ['Star', 'Extra'],
        'last_name': ['WR1', 'WR2'],
        'team': ['M1', 'M2'],
        'p50_weekly': [20.0, 18.0],
        'p90_weekly': [25.0, 22.0],
    }, index=['wr1_my', 'wr2_my'])

    # Partner Team: 2 RBs (20, 18), 0 WRs
    opp_roster = pd.DataFrame({
        'position': ['RB', 'RB'],
        'first_name': ['Star', 'Extra'],
        'last_name': ['RB1', 'RB2'],
        'team': ['O1', 'O2'],
        'p50_weekly': [20.0, 18.0],
        'p90_weekly': [25.0, 22.0],
    }, index=['rb1_opp', 'rb2_opp'])

    opponent_rosters = {
        'opp_1': {
            'name': 'Partner Team',
            'username': 'partner_user',
            'roster': opp_roster,
        }
    }

    weekly_points = pd.DataFrame({
        1: {'wr1_my': 20.0, 'wr2_my': 18.0, 'rb1_opp': 20.0, 'rb2_opp': 18.0},
    })

    recs = compute_trade_recommendations(
        my_roster, opponent_rosters, weekly_points, settings)

    assert not recs.empty
    # Both wr1_my/wr2_my for rb1_opp/rb2_opp trades should improve both teams
    match = recs[(recs['give_player_id'] == 'wr2_my') & (recs['receive_player_id'] == 'rb2_opp')]
    assert not match.empty
    row = match.iloc[0]
    assert row['my_uplift'] == pytest.approx(18.0)
    assert row['partner_uplift'] == pytest.approx(18.0)
    assert bool(row['win_win']) is True


def test_compute_trade_recommendations_one_sided_trade():
    """One-sided trade: My team gains points, but partner team loses points."""
    settings = DraftSettings(teams=12, slots={'RB': 1, 'WR': 1})

    # My Team: 1 WR (10.0), 0 RBs
    my_roster = pd.DataFrame({
        'position': ['WR'],
        'first_name': ['Weak'],
        'last_name': ['WR'],
        'team': ['M1'],
        'p50_weekly': [10.0],
        'p90_weekly': [12.0],
    }, index=['wr_weak_my'])

    # Partner Team: 1 RB (20.0), 1 WR (15.0)
    opp_roster = pd.DataFrame({
        'position': ['RB', 'WR'],
        'first_name': ['Star', 'Good'],
        'last_name': ['RB', 'WR'],
        'team': ['O1', 'O2'],
        'p50_weekly': [20.0, 15.0],
        'p90_weekly': [25.0, 18.0],
    }, index=['rb_star_opp', 'wr_good_opp'])

    opponent_rosters = {
        'opp_1': {
            'name': 'Partner Team',
            'username': 'partner_user',
            'roster': opp_roster,
        }
    }

    weekly_points = pd.DataFrame({
        1: {'wr_weak_my': 10.0, 'rb_star_opp': 20.0, 'wr_good_opp': 15.0},
    })

    recs = compute_trade_recommendations(
        my_roster, opponent_rosters, weekly_points, settings)

    assert not recs.empty
    match = recs[(recs['give_player_id'] == 'wr_weak_my') & (recs['receive_player_id'] == 'rb_star_opp')]
    assert not match.empty
    row = match.iloc[0]
    assert row['my_uplift'] > 0  # My team gains an RB
    assert row['partner_uplift'] < 0  # Partner team loses their star RB
    assert bool(row['win_win']) is False


def test_compute_trade_recommendations_filters_out_non_positive_my_uplift():
    """Trades where my_uplift <= 0 should be filtered out."""
    settings = DraftSettings(teams=12, slots={'RB': 1, 'WR': 1})

    # My Team: 1 star WR (25.0), 1 star RB (25.0)
    my_roster = pd.DataFrame({
        'position': ['WR', 'RB'],
        'first_name': ['Star', 'Star'],
        'last_name': ['WR', 'RB'],
        'team': ['M1', 'M2'],
        'p50_weekly': [25.0, 25.0],
        'p90_weekly': [30.0, 30.0],
    }, index=['wr_star', 'rb_star'])

    # Partner Team: 1 weak WR (2.0)
    opp_roster = pd.DataFrame({
        'position': ['WR'],
        'first_name': ['Weak'],
        'last_name': ['WR'],
        'team': ['O1'],
        'p50_weekly': [2.0],
        'p90_weekly': [3.0],
    }, index=['wr_weak'])

    opponent_rosters = {
        'opp_1': {
            'name': 'Partner Team',
            'username': 'partner_user',
            'roster': opp_roster,
        }
    }

    weekly_points = pd.DataFrame({
        1: {'wr_star': 25.0, 'rb_star': 25.0, 'wr_weak': 2.0},
    })

    recs = compute_trade_recommendations(
        my_roster, opponent_rosters, weekly_points, settings)

    assert recs.empty


def test_compute_trade_recommendations_rest_of_season():
    """Calculates trade uplift starting at current_week."""
    settings = DraftSettings(teams=12, slots={'RB': 1, 'WR': 1})

    my_roster = pd.DataFrame({
        'position': ['WR', 'WR'],
        'first_name': ['WR1', 'WR2'],
        'last_name': ['My', 'My'],
        'team': ['M1', 'M2'],
        'p50_weekly': [20.0, 18.0],
        'p90_weekly': [22.0, 20.0],
    }, index=['wr1_my', 'wr2_my'])

    opp_roster = pd.DataFrame({
        'position': ['RB', 'RB'],
        'first_name': ['RB1', 'RB2'],
        'last_name': ['Opp', 'Opp'],
        'team': ['O1', 'O2'],
        'p50_weekly': [20.0, 18.0],
        'p90_weekly': [22.0, 20.0],
    }, index=['rb1_opp', 'rb2_opp'])

    opponent_rosters = {'opp_1': {'name': 'Partner', 'roster': opp_roster}}

    # Week 1: huge points (should be ignored when current_week=2)
    # Week 2: +10 uplift
    weekly_points = pd.DataFrame({
        1: {'wr1_my': 100.0, 'wr2_my': 100.0, 'rb1_opp': 100.0, 'rb2_opp': 100.0},
        2: {'wr1_my': 20.0, 'wr2_my': 10.0, 'rb1_opp': 20.0, 'rb2_opp': 10.0},
    })

    recs = compute_trade_recommendations(
        my_roster, opponent_rosters, weekly_points, settings, current_week=2)

    assert not recs.empty
    match = recs[(recs['give_player_id'] == 'wr2_my') & (recs['receive_player_id'] == 'rb2_opp')]
    assert not match.empty
    assert match.iloc[0]['my_uplift'] == pytest.approx(10.0)


def test_compute_trade_recommendations_empty_inputs():
    """Handles empty rosters or missing opponent data gracefully."""
    settings = DraftSettings(teams=12, slots={'RB': 1, 'WR': 1})
    weekly_points = pd.DataFrame({1: {'p1': 10.0}})

    assert compute_trade_recommendations(pd.DataFrame(), {}, weekly_points, settings).empty
    assert compute_trade_recommendations(pd.DataFrame({'position': ['RB']}, index=['p1']), {}, weekly_points, settings).empty


def test_render_trade_suggestions_renders_multiple_leagues(monkeypatch):
    """render_trade_suggestions renders headers and fragments for each league."""
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
        '_trade_suggestions_league_fragment',
        lambda league_id, user_id, season, week: rendered_fragments.append((league_id, user_id, week)),
    )

    markdown_calls = []
    monkeypatch.setattr(streamlit_app.st, 'markdown', lambda text: markdown_calls.append(text))
    monkeypatch.setattr(streamlit_app.st, 'title', lambda title: None)

    streamlit_app.render_trade_suggestions('test_user', 1)

    assert rendered_fragments == [('l1', 'user_1', 1), ('l2', 'user_1', 1)]
    assert '## League One' in markdown_calls
    assert '## League Two' in markdown_calls
