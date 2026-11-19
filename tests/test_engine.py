"""Shared conformance fixtures for the engine boundary.

These are the same inputs and expected numbers asserted in `core/src/lineup.rs`
and `core/src/uplift.rs`. Each case names the Rust test it mirrors, so a drift
on either side fails with a matching name instead of a silent numeric shift.
"""
import pandas as pd
import pytest

from streamlit_app import DraftSettings, _best_lineup_score, compute_lineup_uplift

# core::lineup::tests::scores_the_league_lineup_not_the_roster_shape
LEAGUE_SLOTS = ['QB', 'RB', 'RB', 'WR', 'WR', 'TE']
LEAGUE_POSITIONS = ['QB', 'RB', 'RB', 'WR', 'WR', 'WR']
LEAGUE_SCORES = [20.0, 15.0, 10.0, 20.0, 18.0, 12.0]


def test_conformance_every_starting_slot_but_te_filled():
    # A receiver with no slot open adds nothing, so 20+15+10+20+18.
    assert _best_lineup_score(LEAGUE_POSITIONS, LEAGUE_SCORES,
                              LEAGUE_SLOTS) == pytest.approx(83.0)


def test_conformance_extra_receiver_changes_nothing():
    assert _best_lineup_score(LEAGUE_POSITIONS + ['WR'], LEAGUE_SCORES + [12.0],
                              LEAGUE_SLOTS) == pytest.approx(83.0)


def test_conformance_tight_end_fills_the_empty_te_slot():
    assert _best_lineup_score(LEAGUE_POSITIONS + ['WR', 'TE'],
                              LEAGUE_SCORES + [12.0, 15.0],
                              LEAGUE_SLOTS) == pytest.approx(98.0)


def test_conformance_fills_fixed_slots_before_flex():
    # core::lineup::tests::fills_fixed_slots_before_flex
    assert _best_lineup_score(['WR', 'WR', 'RB'], [10.0, 8.0, 20.0],
                              ['WR', 'WR', 'FLEX']) == pytest.approx(38.0)


def test_conformance_bench_slots_score_nothing():
    # core::lineup::tests::bench_slots_accept_anyone_but_score_nothing
    assert _best_lineup_score(['QB', 'RB'], [10.0, 30.0],
                              ['QB', 'BN']) == pytest.approx(10.0)


def _uplift_fixture():
    pool = pd.DataFrame({'position': ['WR'], 'drafted': [False]}, index=['cand'])
    roster = pd.DataFrame({'position': ['RB']}, index=['rb1'])
    weekly = pd.DataFrame({'rb1': [10.0] * 4, 'cand': [1.0, 1.0, 10.0, 10.0]},
                          index=[1, 2, 3, 4]).T
    return pool, weekly, roster, DraftSettings(teams=2, slots={'RB': 1, 'WR': 1})


def test_conformance_playoff_weeks_count_more_than_regular_season_weeks():
    # core::uplift::tests::playoff_weeks_count_more_than_regular_season_weeks
    pool, weekly, roster, settings = _uplift_fixture()

    flat = compute_lineup_uplift(pool, weekly, roster, settings)
    assert flat['cand'] == pytest.approx(5.5)

    weighted = compute_lineup_uplift(pool, weekly, roster, settings,
                                     playoff_week_start=3)
    # (1 + 1 + 1.5*10 + 1.5*10) / 5
    assert weighted['cand'] == pytest.approx(6.4)


def test_conformance_bench_player_adds_nothing_until_a_slot_opens():
    # core::uplift::tests::a_bench_player_adds_nothing_until_a_slot_opens
    pool = pd.DataFrame({'position': ['WR'], 'drafted': [False]}, index=['cand'])
    roster = pd.DataFrame({'position': ['RB', 'WR']}, index=['rb1', 'wr1'])
    weekly = pd.DataFrame({'rb1': [12.0], 'wr1': [9.0], 'cand': [8.0]},
                          index=[1]).T
    settings = DraftSettings(teams=2, slots={'RB': 1, 'WR': 1})

    uplift = compute_lineup_uplift(pool, weekly, roster, settings)
    assert uplift['cand'] == pytest.approx(0.0)
