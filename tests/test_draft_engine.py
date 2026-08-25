import numpy as np
import pandas as pd
import pytest
from streamlit_app import (
    compute_bb_vorp,
    compute_personal_score,
    compute_weekly_lineup_bonus,
    effective_position_needs,
    is_users_turn,
    picks_until_current_turn,
    players_available_at_next_pick,
    DraftData,
    DraftSettings,
    PositionDemand,
)


def test_draft_settings_from_draft_derives_slots_no_hardcoding():
    draft = {
        'settings': {
            'teams': 12,
            'slots_qb': 1,
            'slots_rb': 2,
            'slots_wr': 3,
            'slots_te': 1,
            'slots_flex': 1,
            'slots_super_flex': 1,
            'slots_k': 0,
            'slots_def': 0,
            'slots_bn': 15,
        }
    }
    settings = DraftSettings.from_draft(draft)

    assert settings.teams == 12
    # slots_k/slots_def are 0 so excluded; slots_bn is never a starting spot.
    assert settings.slots == {
        'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 1, 'SUPER_FLEX': 1,
    }
    assert settings.relevant_positions == {'QB', 'RB', 'WR', 'TE'}


def build_pool(rows: dict) -> pd.DataFrame:
    return pd.DataFrame.from_dict(rows, orient='index')


class FakeSettings:
    def __init__(self, relevant_positions, slots=None):
        self.relevant_positions = set(relevant_positions)
        self.slots = slots or {}


def test_find_replacement_rank_detects_largest_relative_drop(monkeypatch):
    monkeypatch.setattr(PositionDemand, 'CLIFF_SEARCH_MIN_RANK', 1)
    # Ranks 1-3 (100,90,80) step down ~10-12% each; rank 3->4 (80->20) is a 75%
    # drop - far larger than any other, so the cliff sits after rank 3.
    values = np.array([100.0, 90.0, 80.0, 20.0, 18.0, 16.0, 14.0])
    assert PositionDemand._find_replacement_rank(values) == 3


def test_find_replacement_rank_ignores_gaps_outside_search_window(monkeypatch):
    monkeypatch.setattr(PositionDemand, 'CLIFF_SEARCH_MIN_RANK', 3)
    # The biggest relative drop is actually rank 1->2, but that's below
    # CLIFF_SEARCH_MIN_RANK (too small a group to call a "cliff") so it's
    # ignored; the largest drop within the allowed window wins instead.
    values = np.array([100.0, 5.0, 4.8, 4.6, 1.0, 0.9])
    assert PositionDemand._find_replacement_rank(values) == 4


def test_position_demand_excludes_zero_production_players(monkeypatch):
    monkeypatch.setattr(PositionDemand, 'CLIFF_SEARCH_MIN_RANK', 1)
    pool = build_pool({
        'te1': {'position': 'TE', 'mean_pts': 100, 'ceiling_90': 120, 'drafted': False},
        'te2': {'position': 'TE', 'mean_pts': 90, 'ceiling_90': 110, 'drafted': False},
        'te3': {'position': 'TE', 'mean_pts': 80, 'ceiling_90': 100, 'drafted': False},
        'te4': {'position': 'TE', 'mean_pts': 20, 'ceiling_90': 30, 'drafted': False},
        **{f'te_zero{i}': {'position': 'TE', 'mean_pts': 0.0, 'ceiling_90': 0.0, 'drafted': False}
           for i in range(20)},
    })
    demand = PositionDemand(pool, FakeSettings({'TE'}, slots={}))
    # The cliff (100,90,80 -> 20, a 75% relative drop) sits at rank 3; a flood of
    # zero-production players is excluded entirely and never distorts this.
    assert demand.loc['TE', 'total_viable'] == 3


def test_position_demand_scarcity_and_remaining(monkeypatch):
    monkeypatch.setattr(PositionDemand, 'CLIFF_SEARCH_MIN_RANK', 1)
    pool = build_pool({
        'te1': {'position': 'TE', 'mean_pts': 100, 'ceiling_90': 120, 'drafted': True},
        'te2': {'position': 'TE', 'mean_pts': 90, 'ceiling_90': 110, 'drafted': False},
        'te3': {'position': 'TE', 'mean_pts': 20, 'ceiling_90': 30, 'drafted': False},
    })
    demand = PositionDemand(pool, FakeSettings({'TE'}, slots={}))

    assert demand.loc['TE', 'total_viable'] == 2      # te1, te2 clear the cliff; te3 doesn't
    assert demand.loc['TE', 'remaining_viable'] == 1  # te1 already drafted
    assert demand.loc['TE', 'replacement_ceiling'] == pytest.approx(110)
    assert demand.loc['TE', 'scarcity_multiplier'] == pytest.approx(2.0)
    assert bool(demand.loc['TE', 'is_cliff']) is False  # strictly > 2.0, not >=


def test_position_demand_cliff_when_position_exhausted(monkeypatch):
    monkeypatch.setattr(PositionDemand, 'CLIFF_SEARCH_MIN_RANK', 1)
    pool = build_pool({
        'te1': {'position': 'TE', 'mean_pts': 100, 'ceiling_90': 120, 'drafted': True},
        'te2': {'position': 'TE', 'mean_pts': 90, 'ceiling_90': 110, 'drafted': True},
        'te3': {'position': 'TE', 'mean_pts': 20, 'ceiling_90': 30, 'drafted': False},
    })
    demand = PositionDemand(pool, FakeSettings({'TE'}, slots={}))

    assert demand.loc['TE', 'remaining_viable'] == 0
    assert demand.loc['TE', 'replacement_ceiling'] == pytest.approx(0.0)
    assert demand.loc['TE', 'scarcity_multiplier'] == float('inf')
    assert bool(demand.loc['TE', 'is_cliff']) is True


def test_position_demand_is_stable_regardless_of_other_positions_talent():
    # A different position's talent curve must never change this position's
    # viable-tier cutoff - each position is ranked strictly against its own
    # population, never in competition with another position.
    settings = FakeSettings({'TE', 'RB'})
    sparse_rb_pool = build_pool({
        'te1': {'position': 'TE', 'mean_pts': 20, 'ceiling_90': 28, 'drafted': False},
        'rb1': {'position': 'RB', 'mean_pts': 5, 'ceiling_90': 8, 'drafted': False},
    })
    loaded_rb_pool = build_pool({
        'te1': {'position': 'TE', 'mean_pts': 20, 'ceiling_90': 28, 'drafted': False},
        'rb1': {'position': 'RB', 'mean_pts': 500, 'ceiling_90': 800, 'drafted': False},
    })

    demand_sparse = PositionDemand(sparse_rb_pool, settings)
    demand_loaded = PositionDemand(loaded_rb_pool, settings)

    assert demand_sparse.loc['TE', 'total_viable'] == demand_loaded.loc['TE', 'total_viable']
    assert demand_sparse.loc['TE', 'replacement_ceiling'] == demand_loaded.loc['TE', 'replacement_ceiling']


def test_position_demand_uses_league_starter_demand():
    pool = build_pool({
        f'qb{i}': {
            'position': 'QB',
            'mean_pts': 100 - i if i < 6 else 20 - i,
            'ceiling_90': 120 - i if i < 6 else 40 - i,
            'drafted': False,
        }
        for i in range(30)
    })
    demand = PositionDemand(
        pool, DraftSettings(teams=12, slots={'QB': 1, 'SUPER_FLEX': 1}))

    assert demand.loc['QB', 'total_viable'] == 24


def test_compute_bb_vorp_uses_players_available_at_next_pick():
    pool = build_pool({
        'qb_now': {'position': 'QB', 'ceiling_90': 30, 'adp': 1, 'drafted': False},
        'qb_next': {'position': 'QB', 'ceiling_90': 20, 'adp': 4, 'drafted': False},
        'rb_now': {'position': 'RB', 'ceiling_90': 26, 'adp': 2, 'drafted': False},
        'rb_next': {'position': 'RB', 'ceiling_90': 25, 'adp': 6, 'drafted': False},
    })

    next_pick_pool = players_available_at_next_pick(pool, picks_until_next_pick=2)
    vorp = compute_bb_vorp(pool, next_pick_pool)

    assert set(next_pick_pool.index) == {'qb_next', 'rb_next'}
    assert vorp['qb_now'] == pytest.approx(10)
    assert vorp['rb_now'] == pytest.approx(1)

def test_weekly_lineup_bonus_rewards_players_who_improve_starting_lineups():
    settings = DraftSettings(teams=1, slots={'RB': 1, 'FLEX': 1})
    pool = build_pool({
        'wr_upgrade': {'position': 'WR', 'drafted': False},
        'qb_ineligible': {'position': 'QB', 'drafted': False},
    })
    weekly_points = pd.DataFrame({
        1: {'rb_owned': 10.0, 'wr_owned': 5.0, 'wr_upgrade': 12.0, 'qb_ineligible': 20.0},
        2: {'rb_owned': 10.0, 'wr_owned': 5.0, 'wr_upgrade': 12.0, 'qb_ineligible': 20.0},
    })
    my_roster = pd.DataFrame.from_dict({
        'rb_owned': {'position': 'RB'},
        'wr_owned': {'position': 'WR'},
    }, orient='index')

    bonus = compute_weekly_lineup_bonus(pool, weekly_points, my_roster, settings)

    assert bonus['wr_upgrade'] == pytest.approx(7.0)
    assert bonus['qb_ineligible'] == pytest.approx(0.0)


@pytest.mark.parametrize("picks_made,user_id,expected", [
    (0, 'u1', True),
    (0, 'u2', False),
    (4, 'u4', True),   # round 2 start, snake-reversed: slot 4 is on the clock
    (4, 'u1', False),
    (7, 'u1', True),   # last pick of round 2, snake-reversed back to slot 1
])
def test_is_users_turn_snake_draft(picks_made, user_id, expected):
    draft = {
        'type': 'snake',
        'settings': {'teams': 4},
        'draft_order': {'u1': 1, 'u2': 2, 'u3': 3, 'u4': 4},
    }
    assert is_users_turn(draft, picks_made, user_id) is expected


def test_is_users_turn_auction_always_true():
    draft = {'type': 'auction', 'settings': {'teams': 4}, 'draft_order': {}}
    assert is_users_turn(draft, 0, 'anyone') is True
    assert is_users_turn(draft, 50, 'anyone') is True


def test_is_users_turn_unknown_user_is_false():
    draft = {
        'type': 'snake',
        'settings': {'teams': 4},
        'draft_order': {'u1': 1, 'u2': 2, 'u3': 3, 'u4': 4},
    }
    assert is_users_turn(draft, 0, 'ghost') is False
def test_picks_until_current_turn_uses_snake_turn_order():
    draft = {
        'type': 'snake',
        'settings': {'teams': 4},
        'draft_order': {'u1': 1, 'u2': 2, 'u3': 3, 'u4': 4},
    }

    assert picks_until_current_turn(draft, 0) == 6
    assert picks_until_current_turn(draft, 1) == 4
    assert picks_until_current_turn(draft, 3) == 0




def test_draft_data_bypasses_network_when_fields_provided():
    import tests.mock as mock
    data = DraftData(draft_id='999', draft=mock.draft(), picks=[mock.pick(player_id='1')])
    assert data.draft['settings']['teams'] == 12
    assert data.picks[0]['player_id'] == '1'


def test_build_player_pool_end_to_end(monkeypatch):
    import tests.mock as mock
    from streamlit_app import Data, build_player_pool

    sleeper_players = pd.DataFrame.from_dict({
        '1': {'position': 'QB', 'first_name': 'A', 'last_name': 'One', 'team': 'AAA'},
        '2': {'position': 'RB', 'first_name': 'B', 'last_name': 'Two', 'team': 'BBB'},
        '3': {'position': 'K', 'first_name': 'C', 'last_name': 'Three', 'team': 'CCC'},
    }, orient='index')
    monkeypatch.setattr(Data, 'get_players', staticmethod(lambda: sleeper_players))

    projections = pd.DataFrame.from_dict({
        '1': {'mean_pts': 20.0, 'ceiling_90': 30.0, 'adp': 10},
        '2': {'mean_pts': 15.0, 'ceiling_90': 22.0, 'adp': 20},
        '3': {'mean_pts': 5.0, 'ceiling_90': 8.0, 'adp': 30},
    }, orient='index')

    settings = DraftSettings(teams=2, slots={'QB': 1, 'RB': 1})
    picks = [mock.pick(player_id='1')]

    pool = build_player_pool(projections, settings, picks, {'AAA': 5, 'BBB': 9})

    # K is filtered out: not a relevant position for this draft's slots.
    assert set(pool.index) == {'1', '2'}
    assert bool(pool.loc['1', 'drafted']) is True
    assert bool(pool.loc['2', 'drafted']) is False
    assert pool.loc['1', 'bye_week'] == 5
    assert pool.loc['2', 'bye_week'] == 9


def test_build_season_projections_excludes_bye_weeks_from_mean_and_ceiling(monkeypatch):
    from streamlit_app import Data, build_season_projections, Z_90TH_PERCENTILE

    # Player '1' plays weeks 1-3 (10, 10, 10 pts); week 2 is a bye for player '2'
    # (absent from that week's projections) and should not drag down their
    # season total or be treated as a zero for variance.
    weekly_stats = {
        1: pd.DataFrame({'1': {'pass_yd': 250, 'adp_dd_ppr': 10}, '2': {'rec_yd': 50, 'adp_dd_ppr': 20}}),
        2: pd.DataFrame({'1': {'pass_yd': 250, 'adp_dd_ppr': 10}}),
        3: pd.DataFrame({'1': {'pass_yd': 250, 'adp_dd_ppr': 10}, '2': {'rec_yd': 50, 'adp_dd_ppr': 20}}),
    }
    monkeypatch.setattr(Data, 'get_projections', staticmethod(lambda season, week: weekly_stats.get(week, pd.DataFrame())))

    scoring = {'pass_yd': 0.04, 'rec_yd': 0.1}
    result = build_season_projections(season=2026, scoring=scoring)

    # Player '1': 3 weeks * (250*0.04=10) = 30 total, zero variance -> ceiling == mean-per-week.
    assert result.loc['1', 'mean_pts'] == pytest.approx(30.0)
    assert result.loc['1', 'ceiling_90'] == pytest.approx(10.0)
    # Player '2': only 2 weeks played (week 2 excluded, not counted as 0) -> total = 2 * 5 = 10.
    assert result.loc['2', 'mean_pts'] == pytest.approx(10.0)
    assert result.loc['2', 'ceiling_90'] == pytest.approx(5.0)
    assert result.loc['1', 'p50_weekly'] == pytest.approx(10.0)
    assert result.loc['2', 'p50_weekly'] == pytest.approx(5.0)
    assert result.loc['1', 'adp'] == pytest.approx(10.0)
    assert result.loc['2', 'adp'] == pytest.approx(20.0)


def test_build_season_projections_skips_empty_weeks(monkeypatch):
    from streamlit_app import Data, build_season_projections

    weekly_stats = {1: pd.DataFrame({'1': {'pass_yd': 100}})}
    monkeypatch.setattr(Data, 'get_projections', staticmethod(lambda season, week: weekly_stats.get(week, pd.DataFrame())))

    result = build_season_projections(season=2026, scoring={'pass_yd': 0.04})
    assert result.loc['1', 'mean_pts'] == pytest.approx(4.0)


def test_fetch_draft_scoring_uses_real_league_when_linked(monkeypatch):
    from streamlit_app import fetch_draft_scoring
    import sleeper_wrapper as sleeper

    class FakeLeague:
        def __init__(self, league_id):
            self.league_id = league_id

        def get_league(self):
            return {'scoring_settings': {'bonus_rec_te': 0.5}}

    monkeypatch.setattr(sleeper, 'League', FakeLeague)
    scoring = fetch_draft_scoring('123')
    assert scoring == {'bonus_rec_te': 0.5}


def test_fetch_draft_scoring_falls_back_when_no_league():
    from streamlit_app import fetch_draft_scoring, DEFAULT_SCORING
    assert fetch_draft_scoring(None) == DEFAULT_SCORING
    assert fetch_draft_scoring('0') == DEFAULT_SCORING


def test_get_user_drafts_returns_id_and_drafts(monkeypatch):
    from streamlit_app import get_user_drafts
    import sleeper_wrapper as sleeper

    class FakeUser:
        def __init__(self, username):
            self.username = username

        def get_user_id(self):
            return 'uid-1'

        def get_all_drafts(self, sport, season):
            return [{'draft_id': 'd1', 'status': 'drafting'}]

    monkeypatch.setattr(sleeper, 'User', FakeUser)
    user_id, drafts = get_user_drafts('someuser', 2026)
    assert user_id == 'uid-1'
    assert drafts == [{'draft_id': 'd1', 'status': 'drafting'}]


def test_compute_personal_score_boosts_unmet_position_need():
    # Settings need 2 RB dedicated starters; user has drafted 0 so far.
    settings = DraftSettings(teams=2, slots={'RB': 2, 'WR': 1})
    pool = pd.DataFrame.from_dict({
        'rb1': {'position': 'RB', 'drafted': False, 'bye_week': 5},
        'wr1': {'position': 'WR', 'drafted': False, 'bye_week': 5},
    }, orient='index')
    bb_vorp = pd.Series({'rb1': 10.0, 'wr1': 10.0})
    my_roster = pd.DataFrame(columns=['position', 'bye_week'])

    score = compute_personal_score(pool, bb_vorp, my_roster, settings=settings)

    # RB: need 2, have 0 -> 1.0 + 2 = 3.0x. WR: need 1, have 0 -> 1.0 + 1 = 2.0x.
    assert score['rb1'] == pytest.approx(30.0)
    assert score['wr1'] == pytest.approx(20.0)


def test_compute_personal_score_superflex_boosts_second_qb_need():
    # 1 dedicated QB slot + 1 SUPER_FLEX (QB-eligible) -> effective QB need is 2,
    # not just the 1 dedicated slot. With 1 QB already owned, still 1 short.
    settings = DraftSettings(teams=12, slots={'QB': 1, 'SUPER_FLEX': 1})
    pool = pd.DataFrame.from_dict({
        'qb2': {'position': 'QB', 'drafted': False, 'bye_week': 9},
    }, orient='index')
    bb_vorp = pd.Series({'qb2': 10.0})
    my_roster = pd.DataFrame.from_dict(
        {'qb_owned': {'position': 'QB', 'bye_week': 5}}, orient='index')

    score = compute_personal_score(pool, bb_vorp, my_roster, settings=settings)

    # Effective need = 1 (dedicated) + 1 (SUPER_FLEX) = 2; have 1 -> still 1.0x boost -> 2.0x total.
    assert score['qb2'] == pytest.approx(20.0)


def test_effective_position_needs_allocates_superflex_to_quarterbacks():
    settings = DraftSettings(
        teams=1,
        slots={'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 1, 'SUPER_FLEX': 1},
    )

    assert effective_position_needs(settings) == {
        'QB': 2,
        'RB': 3,
        'WR': 4,
        'TE': 2,
    }


def test_compute_personal_score_no_boost_once_need_met():
    settings = DraftSettings(teams=2, slots={'RB': 1})
    pool = pd.DataFrame.from_dict({
        'rb2': {'position': 'RB', 'drafted': False, 'bye_week': 9},
    }, orient='index')
    bb_vorp = pd.Series({'rb2': 10.0})
    my_roster = pd.DataFrame.from_dict(
        {'rb_owned': {'position': 'RB', 'bye_week': 5}}, orient='index')

    score = compute_personal_score(pool, bb_vorp, my_roster, settings=settings)

    # Already have the 1 required RB -> multiplier stays at 1.0, no boost and no penalty.
    assert score['rb2'] == pytest.approx(10.0)


def test_compute_personal_score_discounts_bye_week_stacking():
    settings = DraftSettings(teams=2, slots={'WR': 3})
    pool = pd.DataFrame.from_dict({
        'wr_same_bye': {'position': 'WR', 'drafted': False, 'bye_week': 7},
        'wr_diff_bye': {'position': 'WR', 'drafted': False, 'bye_week': 11},
    }, orient='index')
    bb_vorp = pd.Series({'wr_same_bye': 10.0, 'wr_diff_bye': 10.0})
    my_roster = pd.DataFrame.from_dict({
        'wr_owned_1': {'position': 'WR', 'bye_week': 7},
        'wr_owned_2': {'position': 'WR', 'bye_week': 7},
    }, orient='index')

    score = compute_personal_score(pool, bb_vorp, my_roster, settings=settings)

    # Still need 1 more WR (have 2 of 3) -> 2.0x need boost on both candidates.
    # wr_same_bye additionally discounted for stacking onto 2 already-owned bye-7 WRs.
    assert score['wr_diff_bye'] == pytest.approx(20.0)
    assert score['wr_same_bye'] == pytest.approx(20.0 / (1 + 0.15 * 2))
    assert score['wr_same_bye'] < score['wr_diff_bye']


def test_build_my_roster_includes_picks_outside_recommendation_pool(monkeypatch):
    from streamlit_app import Data, build_my_roster

    sleeper_players = pd.DataFrame.from_dict({
        'qb-with-projection': {'position': 'QB', 'first_name': 'Q', 'last_name': 'B', 'team': 'QTM'},
        'k-picked': {'position': 'K', 'first_name': 'K', 'last_name': 'I', 'team': 'KTM'},
    }, orient='index')
    monkeypatch.setattr(Data, 'get_players', staticmethod(lambda: sleeper_players))

    picks = [
        {'player_id': 'qb-with-projection', 'picked_by': 'user'},
        {'player_id': 'k-picked', 'picked_by': 'user'},
        {'player_id': 'missing-projection', 'picked_by': 'user'},
        {'player_id': 'other-team-pick', 'picked_by': 'someone-else'},
    ]

    roster = build_my_roster(picks, 'user', {'QTM': 7, 'KTM': 10})

    # All 3 of the user's own picks show up, including the K and the one Sleeper never projected.
    assert set(roster.index) == {'qb-with-projection', 'k-picked', 'missing-projection'}
    assert roster.loc['qb-with-projection', 'bye_week'] == 7

def test_get_bye_weeks_uses_team_schedule(monkeypatch):
    from streamlit_app import Data

    class Response:
        def __init__(self, teams):
            self.teams = teams

        def raise_for_status(self):
            return None

        def json(self):
            return {
                'events': [{
                    'competitions': [{
                        'competitors': [
                            {'team': {'abbreviation': team}}
                            for team in self.teams
                        ],
                    }],
                }],
            }

    def get_schedule(url, params):
        teams = ['WSH', 'SEA'] if params['week'] != 7 else ['SEA']
        return Response(teams)

    Data.get_bye_weeks.clear()
    monkeypatch.setattr('streamlit_app.requests.get', get_schedule)

    assert Data.get_bye_weeks(2030) == {'WAS': 7}



def test_derive_bye_weeks_requires_exactly_one_absence():
    from streamlit_app import _derive_bye_weeks

    weekly_teams = {
        1: {'AAA', 'BBB'},
        2: {'AAA', 'BBB'},
        3: {'AAA'},
        4: {'AAA', 'BBB'},
    }

    assert _derive_bye_weeks(weekly_teams) == {'BBB': 3}

