"""Throwaway: fuzz the Rust uplift model against compute_lineup_uplift."""
import ctypes
import json
import random
import sys

import pandas as pd

sys.path.insert(0, '.')
from streamlit_app import DraftSettings, compute_lineup_uplift  # noqa: E402

LIB = ctypes.CDLL('core/target/release/libbestball_core.dylib')
LIB.bestball_request.restype = ctypes.c_void_p
LIB.bestball_request.argtypes = [ctypes.c_char_p]
LIB.bestball_string_free.restype = None
LIB.bestball_string_free.argtypes = [ctypes.c_void_p]


def call(request):
    raw = json.dumps(request).encode()
    ptr = LIB.bestball_request(raw)
    try:
        response = json.loads(ctypes.string_at(ptr).decode())
    finally:
        LIB.bestball_string_free(ptr)
    assert 'error' not in response, response
    return response


POSITIONS = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']
SLOT_TYPES = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPER_FLEX', 'K', 'DEF']

random.seed(11)
mismatches = 0
for case in range(120):
    weeks = random.randint(1, 5)
    slot_counts = {slot: random.randint(1, 2)
                   for slot in random.sample(SLOT_TYPES, random.randint(1, 5))}
    settings = DraftSettings(teams=10, slots=slot_counts)
    slot_positions = [slot for slot, count in slot_counts.items() for _ in range(count)]

    roster = [(f'r{i}', random.choice(POSITIONS)) for i in range(random.randint(1, 8))]
    candidates = [(f'c{i}', random.choice(POSITIONS)) for i in range(random.randint(1, 5))]

    scores = {}
    for pid, _ in roster + candidates:
        scores[pid] = {week: round(random.uniform(0, 25), 3) for week in range(1, weeks + 1)}

    weekly_points = pd.DataFrame(
        {week: {pid: values[week] for pid, values in scores.items()}
         for week in range(1, weeks + 1)})
    my_roster = pd.DataFrame(
        {'position': [pos for _, pos in roster]}, index=[pid for pid, _ in roster])
    pool = pd.DataFrame(
        {'position': [pos for _, pos in candidates], 'drafted': [False] * len(candidates)},
        index=[pid for pid, _ in candidates])

    playoff_week_start = random.choice([None, None, 2, 3])
    expected = compute_lineup_uplift(
        pool, weekly_points, my_roster, settings,
        playoff_week_start=playoff_week_start)

    actual = call({
        'op': 'lineup_uplift',
        'slot_positions': slot_positions,
        'roster': [
            {'id': pid, 'position': pos,
             'weekly': [0.0] + [scores[pid][week] for week in range(1, weeks + 1)]}
            for pid, pos in roster
        ],
        'candidates': [
            {'id': pid, 'position': pos,
             'weekly': [0.0] + [scores[pid][week] for week in range(1, weeks + 1)]}
            for pid, pos in candidates
        ],
        'playoff_week_start': playoff_week_start,
        'weeks': weeks,
    })['uplift']

    for pid, _ in candidates:
        if abs(expected[pid] - actual[pid]) > 1e-9:
            mismatches += 1
            if mismatches <= 3:
                print(f'case {case} {pid}: python={expected[pid]} rust={actual[pid]} '
                      f'slots={slot_counts} playoff={playoff_week_start}')

print(f'{mismatches} mismatches over 120 cases')
