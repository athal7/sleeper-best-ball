import pandas as pd
import pytest
from streamlit_app import (
    compute_bb_vorp,
    compute_personal_score,
    compute_weekly_lineup_bonus,
    is_users_turn,
    next_user_pick_number,
    DraftData,
    DraftSettings,
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



def test_compute_bb_vorp_uses_earliest_position_adp_after_next_pick():
    pool = build_pool({
        'qb_now': {'position': 'QB', 'ceiling_90': 30, 'adp': 1, 'drafted': False},
        'qb_replacement': {'position': 'QB', 'ceiling_90': 20, 'adp': 4, 'drafted': False},
        'qb_later': {'position': 'QB', 'ceiling_90': 25, 'adp': 6, 'drafted': False},
        'rb_now': {'position': 'RB', 'ceiling_90': 26, 'adp': 2, 'drafted': False},
        'rb_replacement': {'position': 'RB', 'ceiling_90': 25, 'adp': 6, 'drafted': False},
    })

    vorp = compute_bb_vorp(pool, next_pick_number=3)

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

def test_weekly_lineup_bonus_values_second_qb_in_superflex():
    settings = DraftSettings(teams=1, slots={'QB': 1, 'SUPER_FLEX': 1})
    pool = build_pool({
        'qb_upgrade': {'position': 'QB', 'drafted': False},
    })
    weekly_points = pd.DataFrame({
        1: {'qb_owned': 10.0, 'rb_owned': 8.0, 'qb_upgrade': 12.0},
        2: {'qb_owned': 10.0, 'rb_owned': 8.0, 'qb_upgrade': 12.0},
    })
    my_roster = pd.DataFrame.from_dict({
        'qb_owned': {'position': 'QB'},
        'rb_owned': {'position': 'RB'},
    }, orient='index')

    bonus = compute_weekly_lineup_bonus(pool, weekly_points, my_roster, settings)


def test_weekly_lineup_bonus_weights_playoff_weeks_heavier():
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

    # Week 2 is a playoff week (1.5x weight).
    # Each week gives 7.0 improvement, weighted: 1.0*7.0 + 1.5*7.0 = 17.5 / 2.5 = 7.0
    bonus = compute_weekly_lineup_bonus(
        pool, weekly_points, my_roster, settings, playoff_week_start=2)

    assert bonus['wr_upgrade'] == pytest.approx(7.0)

def test_weekly_lineup_bonus_playoff_weight_amplifies_playoff_week_improvements():
    settings = DraftSettings(teams=1, slots={'RB': 1, 'FLEX': 1})
    pool = build_pool({
        'wr_upgrade': {'position': 'WR', 'drafted': False},
    })
    # Week 1: improvement = 3.0, Week 2 (playoff): improvement = 6.0
    weekly_points = pd.DataFrame({
        1: {'rb_owned': 10.0, 'wr_owned': 5.0, 'wr_upgrade': 8.0},
        2: {'rb_owned': 10.0, 'wr_owned': 5.0, 'wr_upgrade': 11.0},
    })
    my_roster = pd.DataFrame.from_dict({
        'rb_owned': {'position': 'RB'},
        'wr_owned': {'position': 'WR'},
    }, orient='index')

    # Without playoff weighting: (3.0 + 6.0) / 2 = 4.5
    bonus_no_playoff = compute_weekly_lineup_bonus(
        pool, weekly_points, my_roster, settings)
    assert bonus_no_playoff['wr_upgrade'] == pytest.approx(4.5)

    # With playoff weighting (week 2 is 1.5x):
    # (1.0*3.0 + 1.5*6.0) / (1.0 + 1.5) = (3.0 + 9.0) / 2.5 = 12.0 / 2.5 = 4.8
    bonus_playoff = compute_weekly_lineup_bonus(
        pool, weekly_points, my_roster, settings, playoff_week_start=2)
    assert bonus_playoff['wr_upgrade'] == pytest.approx(4.8)

    # Playoff-weighted bonus > unweighted because playoff week has bigger improvement
    assert bonus_playoff['wr_upgrade'] > bonus_no_playoff['wr_upgrade']


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
def test_next_user_pick_number_uses_snake_turn_order():
    draft = {
        'type': 'snake',
        'settings': {'teams': 4},
        'draft_order': {'u1': 1, 'u2': 2, 'u3': 3, 'u4': 4},
    }

    assert next_user_pick_number(draft, 0, 'u1') == 1
    assert next_user_pick_number(draft, 0, 'u2') == 2
    assert next_user_pick_number(draft, 1, 'u1') == 8




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


def test_compute_personal_score_has_no_position_target_boost():
    pool = pd.DataFrame.from_dict({
        'rb1': {'position': 'RB', 'drafted': False, 'bye_week': 5},
        'wr1': {'position': 'WR', 'drafted': False, 'bye_week': 5},
    }, orient='index')
    bb_vorp = pd.Series({'rb1': 10.0, 'wr1': 10.0})
    my_roster = pd.DataFrame(columns=['position', 'bye_week'])

    score = compute_personal_score(pool, bb_vorp, my_roster)

    assert score['rb1'] == pytest.approx(10.0)
    assert score['wr1'] == pytest.approx(10.0)



def test_compute_personal_score_discounts_bye_week_stacking():
    pool = pd.DataFrame.from_dict({
        'wr_same_bye': {'position': 'WR', 'drafted': False, 'bye_week': 7},
        'wr_diff_bye': {'position': 'WR', 'drafted': False, 'bye_week': 11},
    }, orient='index')
    bb_vorp = pd.Series({'wr_same_bye': 10.0, 'wr_diff_bye': 10.0})
    my_roster = pd.DataFrame.from_dict({
        'wr_owned_1': {'position': 'WR', 'bye_week': 7},
        'wr_owned_2': {'position': 'WR', 'bye_week': 7},
    }, orient='index')

    score = compute_personal_score(pool, bb_vorp, my_roster)

    assert score['wr_diff_bye'] == pytest.approx(10.0)
    assert score['wr_same_bye'] == pytest.approx(10.0 / (1 + 0.15 * 2))
    assert score['wr_same_bye'] < score['wr_diff_bye']



def test_compute_personal_score_ignores_position_saturation():
    pool = pd.DataFrame.from_dict({
        'qb4': {'position': 'QB', 'drafted': False, 'bye_week': 5},
        'rb1': {'position': 'RB', 'drafted': False, 'bye_week': 5},
    }, orient='index')
    bb_vorp = pd.Series({'qb4': 10.0, 'rb1': 10.0})
    my_roster = pd.DataFrame.from_dict({
        'qb1': {'position': 'QB', 'bye_week': 8},
        'qb2': {'position': 'QB', 'bye_week': 9},
        'qb3': {'position': 'QB', 'bye_week': 10},
    }, orient='index')

    score = compute_personal_score(pool, bb_vorp, my_roster)

    assert score['qb4'] == pytest.approx(10.0)
    assert score['rb1'] == pytest.approx(10.0)


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

