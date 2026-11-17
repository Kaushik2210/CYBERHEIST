"""Challenge logic and solvability across seeds."""
import pytest

from challenges import encryption as enc
from challenges import firewall
from challenges import escape as esc
from challenges import network as net


# -- escape ----------------------------------------------------------------------
def test_escape_correct_option_always_present():
    for seed in range(500):
        seq = esc.generate(GameRNG(seed), rounds=5)
        for r in seq.rounds:
            if r.kind == "choice":
                assert r.answer in r.options and len(set(r.options)) == 3
            else:
                assert len(r.answer) == 4 and all(c in esc.CODE_CHARS for c in r.answer)


def test_escape_perfect_play_survives_500_seeds():
    for seed in range(500):
        rng = GameRNG(seed)
        seq = esc.generate(rng, rounds=rng.randint(1, 6), slack=rng.randint(0, 4))
        while seq.current and not seq.out_of_time:
            assert seq.answer(seq.solver_answer())
        assert seq.escaped and not seq.out_of_time, f"escape failed at seed {seed}"


def test_escape_accepts_number_or_text_and_penalises_misses():
    seq = esc.generate(GameRNG(11), rounds=1, slack=0)
    r = seq.current
    if r.kind == "choice":
        assert r.is_correct(str(r.options.index(r.answer) + 1))
        assert r.is_correct(r.answer.lower())
    else:
        assert r.is_correct(r.answer.lower())
    assert not seq.answer("definitely wrong")
    assert seq.failures == 1 and seq.elapsed == 4 and seq.out_of_time
from challenges import password as pw
from core.rng import GameRNG
from core.state import load_config


# -- network ---------------------------------------------------------------------
def test_network_scan_reveals_layers_then_hidden():
    m = net.generate(GameRNG(1), hidden_nodes=2)
    assert m.discovered == {"INTERNET"} and m.routes() == []
    assert m.scan() == ["FIREWALL"]
    assert m.scan() == ["GATEWAY"]
    assert m.scan() == ["SERVER-A", "SERVER-B"]
    assert m.scan() == ["BACKUP", "DATABASE"]
    assert not m.found_hidden()
    assert set(m.scan()) == {"RELAY-7", "PROXY-X"}
    assert m.fully_mapped and m.found_hidden() and m.scan() == []


def test_network_routes_are_valid_paths():
    for seed in range(100):
        m = net.generate(GameRNG(seed), target=GameRNG(seed).choice(["DATABASE", "BACKUP"]))
        while not m.fully_mapped:
            m.scan()
        routes = m.routes()
        assert routes and routes == sorted(routes, key=lambda r: (r.risk, len(r.nodes), r.nodes))
        for r in routes:
            assert r.nodes[0] == "INTERNET" and r.nodes[-1] == m.target
            assert len(set(r.nodes)) == len(r.nodes)
            assert all(frozenset(p) in m.edges for p in zip(r.nodes, r.nodes[1:]))
            assert r.rating in ("LOW", "MEDIUM", "HIGH")


def test_route_detection_costs():
    cfg = load_config()["detection"]
    rng = GameRNG(3)
    assert net.route_detection("LOW", rng, cfg) == 0
    assert net.route_detection("MEDIUM", rng, cfg) == cfg["medium_route"]
    for _ in range(50):
        assert 10 <= net.route_detection("HIGH", rng, cfg) <= 20


def test_network_solvable_500_seeds():
    for seed in range(500):
        rng = GameRNG(seed)
        m = net.generate(rng, target=rng.choice(["DATABASE", "BACKUP"]), hidden_nodes=rng.randint(0, 2))
        for cmd in m.solver_commands():
            if cmd == "scan":
                m.scan()
        assert m.routes(), f"no route at seed {seed}"


# -- password --------------------------------------------------------------------
def test_password_feedback_marks():
    assert pw.feedback("ORBIT42!", "ORBIT42!") == "++++++++"
    assert pw.feedback("ORBIT42!", "TIBRO24!") == "~~+~~~~+"
    assert pw.feedback("RADAR", "AAAAA") == ".+.+."
    assert pw.feedback("RADAR", "RRXXX") == "+~..."


def test_password_validation():
    p = pw.generate(GameRNG(4))
    assert p.validate("x") is not None
    bad_digit = p.mask.replace("W", "A").replace("D", "A").replace("S", p.symbols[0])
    assert "Digits" in p.validate(bad_digit)
    assert p.validate(p.secret) is None
    assert p.validate(p.secret.lower()) is None


def test_password_clues_are_true():
    for seed in range(100):
        p = pw.generate(GameRNG(seed))
        word = "".join(c for c, m in zip(p.secret, p.mask) if m == "W")
        digits = [int(c) for c, m in zip(p.secret, p.mask) if m == "D"]
        sym = "".join(c for c, m in zip(p.secret, p.mask) if m == "S")
        assert word in p.words and sym in p.symbols
        assert all(lo <= d <= hi for d, (lo, hi) in zip(digits, p.digit_ranges))


def test_password_reveal_and_override():
    p = pw.generate(GameRNG(5))
    i, ch = p.reveal_position()
    assert p.secret[i] == ch
    n = p.remaining
    p.add_attempt()
    assert p.remaining == n + 1


def _autoplay_pw(p):
    while p.remaining > 0:
        p.guess(p.next_solver_guess())
        if p.solved:
            return True
    return False


def test_password_solvable_500_seeds():
    for seed in range(500):
        assert _autoplay_pw(pw.generate(GameRNG(seed))), f"password unsolvable at seed {seed}"


def test_password_hard_params_solvable():
    for seed in range(200):
        p = pw.generate(GameRNG(seed), word_count=16, digits=3, symbol_count=6, range_width=5, attempts=5)
        assert _autoplay_pw(p), f"hard password unsolvable at seed {seed}"


# -- encryption ------------------------------------------------------------------
@pytest.mark.parametrize("text", ["NEON GHOST", "ZERO MERIDIAN", "A B C"])
def test_cipher_round_trips(text):
    for s in (1, 13, 25):
        assert enc.caesar(enc.caesar(text, s), -s) == text
    for key in ("NOVA", "ZENITH"):
        assert enc.vigenere(enc.vigenere(text, key), key, decrypt=True) == text
    letters = list(enc.A)
    GameRNG(3).shuffle(letters)
    fwd = dict(zip(enc.A, letters))
    back = {v: k for k, v in fwd.items()}
    assert enc.substitute(enc.substitute(text, fwd), back) == text
    assert enc.from_binary(enc.to_binary(text)) == text
    assert enc.from_hex(enc.to_hex(text)) == text


def test_cipher_answer_normalization_and_attempts():
    p = enc.generate(GameRNG(7), "caesar", attempts=2)
    assert not p.check("wrong") and p.remaining == 1
    assert p.check(p.answer.lower() + "  ")
    assert p.solved


def test_cipher_hints_and_tools():
    p = enc.generate(GameRNG(8), "caesar")
    assert p.tool(str(p.shift)).endswith(p.answer)
    assert "Usage" in p.tool("abc")
    seen = [p.next_hint() for _ in range(len(p.hints))]
    assert all(seen) and p.next_hint() is None
    v = enc.generate(GameRNG(9), "vigenere")
    assert v.tool(v.key).endswith(v.answer)


@pytest.mark.parametrize("kind", enc.KINDS)
def test_cipher_solvable_500_seeds(kind):
    for seed in range(500):
        p = enc.generate(GameRNG(seed), kind)
        assert p.check(p.solver_answer()), f"{kind} unsolvable at seed {seed}"


@pytest.mark.parametrize("kind", enc.KINDS)
def test_tough_cipher_solvable_500_seeds(kind):
    for seed in range(500):
        p = enc.generate(GameRNG(seed), kind, tough=True)
        assert p.check(p.solver_answer()), f"tough {kind} unsolvable at seed {seed}"


def test_tough_vigenere_hides_key_but_crib_recovers_it():
    for seed in range(200):
        p = enc.generate(GameRNG(seed), "vigenere", tough=True)
        assert p.key not in p.brief and p.crib in p.brief and f"Key length: {p.key_len}" in p.brief
        assert p.key_len <= len(p.crib)
        assert enc.key_from_crib(p.ciphertext, p.crib, p.key_len) == p.key


def test_tough_mode_drops_giveaway_hints():
    for seed in range(100):
        c = enc.generate(GameRNG(seed), "caesar", tough=True)
        assert not any(h == f"The shift is {c.shift}." for h in c.hints)
        assert len(enc.caesar_candidates(c.ciphertext)) == 1
        h = enc.generate(GameRNG(seed), "hex", tough=True)
        assert not any("starts with" in x for x in h.hints) and len(h.answer) > 4


def test_layered_cipher_tools():
    p = enc.generate(GameRNG(12), "layered", tough=True)
    layer = p.tool("", "unhex").split(": ", 1)[1]
    assert layer == enc.from_hex(p.ciphertext)
    assert p.tool(str(p.shift), "shift").endswith(p.answer)
    assert "No lab tool" in p.tool("NOVA", "apply")


def test_pattern_solver_handles_tough_rules():
    assert enc._next_term("2, 5, 10, 13, 26") == 29        # +3, x2 alternating
    assert enc._next_term("1, 8, 27, 64, 125") == 216      # cubes
    assert enc._next_term("4, 9, 16, 25, 36") == 49        # squares


def test_substitution_answer_is_unique_among_candidates():
    for seed in range(200):
        p = enc.generate(GameRNG(seed), "substitution")
        shape = enc.letter_pattern(p.ciphertext)
        assert [c for c in p.candidates if enc.letter_pattern(c) == shape] == [p.answer]


# -- firewall --------------------------------------------------------------------
def test_firewall_feedback():
    assert firewall.score((0, 1, 2, 3), (0, 1, 2, 3)) == (4, 0)
    assert firewall.score((0, 1, 2, 3), (3, 2, 1, 0)) == (0, 4)
    assert firewall.score((0, 1, 2, 3), (0, 2, 4, 5)) == (1, 1)
    assert firewall.score((0, 1, 2, 3), (4, 5, 6, 7)) == (0, 0)


def test_firewall_feedback_with_repeated_rules():
    assert firewall.score((0, 0, 1, 1), (0, 1, 0, 1)) == (2, 2)
    assert firewall.score((0, 0, 0, 1), (0, 0, 0, 0)) == (3, 0)
    assert firewall.score((2, 2, 3, 3), (3, 3, 2, 2)) == (0, 4)
    assert firewall.score((1, 2, 3, 4), (1, 1, 1, 1)) == (1, 0)


def test_firewall_repeats_parse_and_tight_attempts():
    p = firewall.generate(GameRNG(3), pool_size=6, length=4, attempts=99, repeats=True, margin=1)
    assert p.parse("1 1 2 2") == (0, 0, 1, 1)
    assert p.attempts == p.par + 1
    loose = firewall.generate(GameRNG(3), pool_size=6, length=4, attempts=99)
    assert isinstance(loose.parse("1 1 2 2"), str) and loose.attempts == 99


def test_firewall_tight_repeats_solvable_500_seeds():
    for seed in range(500):
        p = firewall.generate(GameRNG(seed), pool_size=6, length=4, attempts=0, repeats=True, margin=0)
        assert _autoplay(p), f"tight repeat firewall unsolvable at seed {seed}"
        assert len(p.history) == p.par


def test_firewall_hard_repeats_length5_solvable():
    for seed in range(15):
        p = firewall.generate(GameRNG(seed), pool_size=6, length=5, attempts=0, repeats=True, margin=1)
        assert _autoplay(p) and len(p.history) <= p.attempts


def test_firewall_parse_rejects_bad_input():
    p = firewall.generate(GameRNG(1), pool_size=6, length=4, attempts=10)
    assert isinstance(p.parse("1 2 3"), str)
    assert isinstance(p.parse("1 2 3 x"), str)
    assert isinstance(p.parse("1 2 3 9"), str)
    assert isinstance(p.parse("1 1 2 3"), str)
    assert p.parse("1, 2, 3, 4") == (0, 1, 2, 3)


def test_firewall_reveal_and_override():
    p = firewall.generate(GameRNG(2), pool_size=6, length=4, attempts=8)
    slot, tok = p.reveal_slot()
    assert p.secret[slot] == tok
    before = p.remaining
    p.add_attempt()
    assert p.remaining == before + 1


def _autoplay(p: firewall.FirewallPuzzle) -> bool:
    while p.remaining > 0:
        p.guess(p.parse(p.next_solver_guess()))
        if p.solved:
            return True
    return False


def test_firewall_solvable_500_seeds():
    for seed in range(500):
        p = firewall.generate(GameRNG(seed), pool_size=6, length=4, attempts=6)
        assert _autoplay(p), f"unsolvable firewall at seed {seed}"


def test_firewall_hard_params_solvable():
    for seed in range(40):
        p = firewall.generate(GameRNG(seed), pool_size=8, length=5, attempts=7)
        assert _autoplay(p), f"unsolvable hard firewall at seed {seed}"
