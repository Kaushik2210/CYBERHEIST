"""Player profile: XP to level, reputation, counters and alias validation."""
import pytest

from core.player import Player, validate_alias
from core.progression import level_for_xp, title_for_level, xp_to_next
from core.state import load_config

PROG = load_config()["progression"]
TH, TITLES = PROG["xp_thresholds"], PROG["level_titles"]


@pytest.mark.parametrize("xp,level", [(0, 1), (299, 1), (300, 2), (799, 2), (800, 3), (4500, 6),
                                       (9999, 7), (10000, 8), (99999, 8)])
def test_xp_to_level(xp, level):
    assert level_for_xp(xp, TH) == level


def test_titles_and_xp_to_next():
    assert [title_for_level(n, TITLES) for n in (1, 8)] == ["Script Kiddie", "Zero Day Legend"]
    assert xp_to_next(250, TH) == 50 and xp_to_next(10000, TH) is None


def test_add_xp_levels_up_and_ignores_negative():
    p = Player(alias="Neo_01")
    assert p.add_xp(350, TH) and p.level == 2 and p.title(TITLES) == "Packet Sniffer"
    assert not p.add_xp(-500, TH) and p.xp == 350


def test_reputation_and_credits_are_clamped():
    p = Player(alias="Neo_01", credits=100)
    p.adjust_reputation(-20)
    assert p.reputation == 0
    p.adjust_reputation(5000)
    assert p.reputation == 1000
    p.add_credits(-1000)
    assert p.credits == 0


def test_success_and_failure_counters():
    p = Player(alias="Neo_01")
    p.record_success(first_clear=True)
    p.record_success(first_clear=False)
    p.record_failure()
    assert (p.successes, p.missions_completed, p.failures) == (2, 1, 1)


@pytest.mark.parametrize("alias,ok", [("Neo", True), ("Neo_01-x", True), ("A" * 16, True),
                                       ("ab", False), ("A" * 17, False), ("bad alias", False), ("x!y", False)])
def test_alias_validation(alias, ok):
    assert (validate_alias(alias) is None) == ok


def test_round_trip_dict():
    p = Player(alias="Neo_01", xp=1234, credits=5, last_seed=9)
    assert Player.from_dict({**p.to_dict(), "unknown": 1}) == p
