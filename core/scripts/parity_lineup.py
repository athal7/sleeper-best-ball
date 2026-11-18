"""Throwaway: fuzz the Rust core against the Python implementation."""
import ctypes
import json
import random
import sys

sys.path.insert(0, '.')
from streamlit_app import _best_lineup_score  # noqa: E402

LIB = ctypes.CDLL('core/target/release/libbestball_core.dylib')
LIB.bestball_request.restype = ctypes.c_void_p
LIB.bestball_request.argtypes = [ctypes.c_char_p]
LIB.bestball_string_free.restype = None
LIB.bestball_string_free.argtypes = [ctypes.c_void_p]


def core_score(slot_positions, players):
    request = json.dumps({
        'op': 'best_lineup_score',
        'slot_positions': slot_positions,
        'players': players,
    }).encode()
    ptr = LIB.bestball_request(request)
    try:
        response = json.loads(ctypes.string_at(ptr).decode())
    finally:
        LIB.bestball_string_free(ptr)
    assert 'error' not in response, response
    return response


POSITIONS = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']
SLOT_TYPES = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPER_FLEX', 'K', 'DEF']

random.seed(7)
mismatches = 0
for case in range(400):
    slot_positions = []
    for slot in random.sample(SLOT_TYPES, random.randint(1, 6)):
        slot_positions.extend([slot] * random.randint(1, 3))
    roster = [
        (f'p{i}', random.choice(POSITIONS), round(random.uniform(0, 30), 3))
        for i in range(random.randint(0, 14))
    ]
    players = [{'id': pid, 'position': pos, 'score': score} for pid, pos, score in roster]

    expected = _best_lineup_score([p for _, p, _ in roster],
                                  [s for _, _, s in roster],
                                  slot_positions)
    actual = core_score(slot_positions, players)
    if abs(expected - actual['score']) > 1e-9:
        mismatches += 1
        if mismatches <= 3:
            print(f'case {case}: python={expected} rust={actual["score"]} slots={slot_positions}')

print(f'{mismatches} mismatches over 400 cases')
