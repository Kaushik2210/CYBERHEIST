"""Black market purchases, funds checks, equip limits and consumable use counts."""
from cyberheist.core.player import Player
from cyberheist.core.state import load_config
from cyberheist.systems.black_market import BlackMarket
from cyberheist.systems.inventory import Inventory

CFG = load_config()
ITEMS = CFG["items"]


def setup(credits=10_000):
    return Player(alias="tester", credits=credits), Inventory(ITEMS, CFG["max_equipped"]), BlackMarket(ITEMS)


def test_default_prices_match_spec():
    prices = {k: v["price"] for k, v in ITEMS.items()}
    assert prices == {"ghost_proxy": 2000, "cipher_toolkit": 800, "neural_accelerator": 2500,
                      "signal_mask": 1800, "quantum_decoder": 1200, "data_scanner": 1000,
                      "emergency_override": 1500}


def test_purchase_deducts_credits():
    p, inv, m = setup(3000)
    ok, _ = m.buy(p, inv, "ghost_proxy")
    assert ok and p.credits == 1000 and inv.owns("ghost_proxy")


def test_insufficient_funds_rejected_without_charge():
    p, inv, m = setup(500)
    ok, msg = m.buy(p, inv, "neural_accelerator")
    assert not ok and "Not enough credits" in msg and p.credits == 500 and not inv.owns("neural_accelerator")


def test_cannot_buy_passive_twice_or_unknown_item():
    p, inv, m = setup()
    m.buy(p, inv, "signal_mask")
    ok, msg = m.buy(p, inv, "signal_mask")
    assert not ok and "already own" in msg and p.credits == 10_000 - 1800
    assert m.buy(p, inv, "laser_sword") == (False, "No such item.")


def test_resolve_by_number_or_id():
    m = BlackMarket(ITEMS)
    assert m.resolve("1") == "ghost_proxy" and m.resolve("data_scanner") == "data_scanner"
    assert m.resolve("0") is None and m.resolve("99") is None and m.resolve("junk") is None


def test_equip_limit_is_two():
    p, inv, m = setup()
    for iid in ("ghost_proxy", "neural_accelerator", "signal_mask"):
        m.buy(p, inv, iid)
    assert inv.equip("ghost_proxy")[0] and inv.equip("neural_accelerator")[0]
    ok, msg = inv.equip("signal_mask")
    assert not ok and "slots are full" in msg
    assert inv.unequip("ghost_proxy")[0] and inv.equip("signal_mask")[0]
    assert inv.loadout() == {"ghost_proxy": False, "neural": True, "signal_mask": True}


def test_consumables_cannot_be_equipped():
    p, inv, m = setup()
    m.buy(p, inv, "cipher_toolkit")
    assert not inv.equip("cipher_toolkit")[0]


def test_consumable_use_counts_stack_and_run_out():
    p, inv, m = setup()
    m.buy(p, inv, "cipher_toolkit")
    assert inv.uses("cipher_toolkit") == 5
    m.buy(p, inv, "cipher_toolkit")
    assert inv.uses("cipher_toolkit") == 10
    m.buy(p, inv, "emergency_override")
    assert inv.consume("emergency_override") and not inv.owns("emergency_override")
    assert not inv.consume("emergency_override")
    assert not inv.consume("ghost_proxy")


def test_inventory_round_trips_through_save_rows():
    p, inv, m = setup()
    m.buy(p, inv, "ghost_proxy")
    inv.equip("ghost_proxy")
    m.buy(p, inv, "data_scanner")
    restored = Inventory(ITEMS, 2, inv.to_rows())
    assert restored.to_rows() == inv.to_rows()
    trimmed = Inventory(ITEMS, 1, {"ghost_proxy": {"uses": 1, "equipped": 1},
                                   "signal_mask": {"uses": 1, "equipped": 1}, "bogus": {"uses": 3, "equipped": 0}})
    assert len(trimmed.equipped()) == 1 and "bogus" not in trimmed.rows
