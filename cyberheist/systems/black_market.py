"""Black market: buy gear with credits. Prices come from settings.json."""
from __future__ import annotations

from typing import Any

from cyberheist.core.player import Player
from cyberheist.systems.inventory import Inventory


class BlackMarket:
    """Sells the items defined in the ``items`` block of settings.json."""

    def __init__(self, items_cfg: dict[str, dict[str, Any]]) -> None:
        """Create the market from item config."""
        self.cfg = items_cfg

    def ids(self) -> list[str]:
        """Item ids in display order."""
        return list(self.cfg)

    def resolve(self, choice: str) -> str | None:
        """Map a menu number (1-based) or item id to an item id."""
        choice = choice.strip().lower()
        if choice.isdigit():
            i = int(choice) - 1
            return self.ids()[i] if 0 <= i < len(self.ids()) else None
        return choice if choice in self.cfg else None

    def listing(self, inventory: Inventory) -> list[tuple[Any, ...]]:
        """Rows for the market table: #, name, price, kind, uses per buy, owned."""
        rows = []
        for n, iid in enumerate(self.ids(), 1):
            c = self.cfg[iid]
            if inventory.kind(iid) == "passive":
                owned = "EQUIPPED" if iid in inventory.equipped() else ("owned" if inventory.owns(iid) else "-")
            else:
                owned = f"x{inventory.uses(iid)}" if inventory.owns(iid) else "-"
            rows.append((n, c["name"], f"{c['price']:,} cr", c["kind"], c["uses"], owned, c["desc"]))
        return rows

    def buy(self, player: Player, inventory: Inventory, iid: str) -> tuple[bool, str]:
        """Buy one item. Checks the id, duplicate passives and funds before charging."""
        if iid not in self.cfg:
            return False, "No such item."
        c = self.cfg[iid]
        if c["kind"] == "passive" and inventory.owns(iid):
            return False, f"You already own {c['name']}."
        if player.credits < c["price"]:
            return False, f"Not enough credits: {c['name']} costs {c['price']:,}, you have {player.credits:,}."
        player.credits -= c["price"]
        inventory.add(iid)
        return True, f"Bought {c['name']} for {c['price']:,} cr."
