"""Items inside missions: passives from the loadout, consumables via 'use <item>'."""
from challenges import encryption, firewall
from core.rng import GameRNG
from core.state import load_config
from interface.theme import Theme
from interface.ui import UI, ScriptedIO
from missions.mission_runner import MissionContext, run_stages
from systems.inventory import Inventory

CFG = load_config()


def make(inputs=(), owned=(), equip=(), seed=1):
    inv = Inventory(CFG["items"], CFG["max_equipped"])
    for iid in owned:
        inv.add(iid)
    for iid in equip:
        inv.equip(iid)
    io = ScriptedIO(inputs)
    ctx = MissionContext(UI(io, Theme(color=False, unicode=False), animations=False),
                         GameRNG(seed), CFG, inventory=inv)
    return ctx, inv, io


def test_equipped_passives_apply():
    ctx, _, _ = make(owned=["ghost_proxy", "neural_accelerator"], equip=["ghost_proxy", "neural_accelerator"])
    assert abs(ctx.meter.mult - 0.7) < 1e-9 and abs(ctx.tick_mult - 0.8) < 1e-9
    ctx2, _, _ = make(owned=["ghost_proxy"])
    assert ctx2.meter.mult == 1.0
    ctx3, _, _ = make(owned=["signal_mask"], equip=["signal_mask"])
    assert ctx3.meter.alarm() == (0.0, True)


def test_decoder_and_override_on_firewall():
    seed = 4
    p = firewall.generate(GameRNG(seed).fork("firewall"), 6, 4, 8)
    answer = " ".join(str(i + 1) for i in p.secret)
    ctx, inv, io = make(["use decoder", "use override", answer],
                        owned=["quantum_decoder", "emergency_override"], seed=seed)
    run_stages(ctx, [{"type": "firewall", "params": {"pool": 6, "length": 4, "attempts": 8}}])
    out = io.text()
    assert "Decoder: slot" in out and "Override: +1 attempt (9 left)" in out
    assert inv.uses("quantum_decoder") == 2 and not inv.owns("emergency_override")
    assert ctx.items_used == ["quantum_decoder", "emergency_override"]


def test_toolkit_hint_costs_no_ticks():
    seed = 6
    p = encryption.generate(GameRNG(seed).fork("cipher-caesar"), "caesar", 3)
    ctx, inv, io = make(["use toolkit", p.answer], owned=["cipher_toolkit"], seed=seed)
    run_stages(ctx, [{"type": "cipher", "params": {"kind": "caesar"}}])
    assert "Toolkit hint" in io.text() and inv.uses("cipher_toolkit") == 4 and ctx.ticks == 1


def test_decoder_on_password_reveals_character():
    ctx, inv, io = make(owned=["quantum_decoder"])
    from challenges import password
    ctx.puzzle, ctx.stage_kind = password.generate(GameRNG(2)), "password"
    assert ctx.use_item("decoder") and "character" in io.text() and inv.uses("quantum_decoder") == 2


def test_no_effect_keeps_charge_and_bad_names_are_handled():
    ctx, inv, io = make(owned=["emergency_override", "data_scanner"])
    assert not ctx.use_item("override") and inv.uses("emergency_override") == 1
    assert not ctx.use_item("scanner") and inv.uses("data_scanner") == 3
    assert not ctx.use_item("decoder") and "no Quantum Decoder left" in io.text()
    assert not ctx.use_item("ghost_proxy") and not ctx.use_item("banana")
    assert "Usable items" in io.text()


def test_inv_command_lists_items():
    ctx, _, io = make(["inv", "x"], owned=["cipher_toolkit", "ghost_proxy"], equip=["ghost_proxy"])
    assert ctx.ask("t") == "x"
    out = io.text()
    assert "Equipped: Ghost Proxy" in out and "Cipher Toolkit x5 (use toolkit)" in out
