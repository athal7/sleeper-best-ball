from streamlit_app import Player
from dataclasses import asdict
import pandas as pd
import pytest

default = Player(
    first_name="Jane",
    last_name="Smith",
    position="RB",
    team="DAL",
    opponent='NYG',
    points=0.0,
    projection=15.5,
    optimistic=20.0,
    pct_played=0.0,
    game_status='9/08 1:00 PM ET',
    game_time='2024-09-08 13:00:00+00:00',
    home=False,
    score=0,
    opponent_score=0,
    injury_status=None,
    bye=False,
)


def player(**kwargs) -> Player:
    data = asdict(default)
    data.update(kwargs)
    return Player(**data)


def test_name():
    assert player().name == "J. Smith"


@pytest.mark.parametrize("player, expected", [
    (player(), f"Sun 1:00 PM @ NYG"),
    (player(home=True), f"Sun 1:00 PM vs NYG"),
    (player(bye=True), "Bye"),
    (player(game_status='5:00 4th Q', pct_played=50,
     score=14, opponent_score=7), f"5:00 4th Q 14-7 @ NYG"),
    (player(game_status='Final', pct_played=100,
     score=21, opponent_score=14), f"Final 21-14 @ NYG"),
])
def test_get_status(player, expected):
    assert player.get_status() == expected


@pytest.mark.parametrize("player, expected", [
    (player(), False),
    (player(pct_played=0.5), True),
    (player(pct_played=1), False),
])
def test_is_live(player, expected):
    assert player.is_live is expected

@pytest.mark.parametrize("player, expected", [
    (player(), False),
    (player(pct_played=0.5), False),
    (player(pct_played=1), True),
])
def test_is_final(player, expected):
    assert player.is_final is expected

@pytest.mark.parametrize("player, expected", [
    (player(), "-"),
    (player(points=10.0), "10.00"),
])
def test_get_points(player, expected):
    assert player.get_points() == expected

@pytest.mark.parametrize("player, expected", [
    (player(), "20.00"),
    (player(projection=0.0), "-"),
    (player(pct_played=1), "15.50"),
])
def test_get_projection(player, expected):
    assert player.get_projection() == expected


@pytest.mark.parametrize("player, expected", [
    (player(), "RB - DAL"),
    (player(injury_status='IR'), "RB - DAL (IR)"),
    (player(injury_status='Questionable'), "RB - DAL (Q)"),
])
def test_player_info(player, expected):
    assert player.player_info == expected