"""Player inventory: consumable charges and equippable passives."""
from __future__ import annotations

from typing import Any


class Inventory:
    """Owned items. Rows match the save format: ``{item_id: {"uses": n, "equipped": 0|1}}``."""

    def __init__(self, items_cfg: dict[str, dict[str, Any]], max_equipped: int = 2,
                 rows: dict[str, dict[str, int]] | None = None) -> None:
        """Create an inventory, optionally restoring saved rows (unknown items are dropped)."""
        self.cfg = items_cfg
        self.max_equipped = max_equipped
        self.rows: dict[str, dict[str, int]] = {}
        for iid, row in (rows or {}).items():
            if iid in self.cfg and row.get("uses", 0) > 0:
                self.rows[iid] = {"uses": int(row["uses"]), "equipped": int(bool(row.get("equipped")))}
        while len(self.equipped()) > self.max_equipped:
            self.rows[self.equipped()[-1]]["equipped"] = 0

    def kind(self, iid: str) -> str:
        """'passive' or 'consumable'."""
        return self.cfg[iid]["kind"]

    def owns(self, iid: str) -> bool:
        """True if the item is held with at least one use."""
        return self.rows.get(iid, {}).get("uses", 0) > 0

    def uses(self, iid: str) -> int:
        """Remaining uses (passives count as 1)."""
        return self.rows.get(iid, {}).get("uses", 0)

    def add(self, iid: str) -> None:
        """Add one purchase: passives become owned, consumables gain their configured uses."""
        row = self.rows.setdefault(iid, {"uses": 0, "equipped": 0})
        if self.kind(iid) == "passive":
            row["uses"] = 1
        else:
            row["uses"] += int(self.cfg[iid]["uses"])

    def equipped(self) -> list[str]:
        """Ids of equipped passives."""
        return [iid for iid, r in self.rows.items() if r["equipped"]]

    def equip(self, iid: str) -> tuple[bool, str]:
        """Equip a passive, respecting the slot limit."""
        if not self.owns(iid):
            return False, "You don't own that item."
        if self.kind(iid) != "passive":
            return False, "Only passive gear can be equipped. Consumables are used in missions."
        if self.rows[iid]["equipped"]:
            return False, "Already equipped."
        if len(self.equipped()) >= self.max_equipped:
            return False, f"All {self.max_equipped} slots are full. Unequip something first."
        self.rows[iid]["equipped"] = 1
        return True, f"{self.cfg[iid]['name']} equipped."

    def unequip(self, iid: str) -> tuple[bool, str]:
        """Unequip a passive."""
        if not self.rows.get(iid, {}).get("equipped"):
            return False, "That item isn't equipped."
        self.rows[iid]["equipped"] = 0
        return True, f"{self.cfg[iid]['name']} unequipped."

    def consume(self, iid: str) -> bool:
        """Spend one charge of a consumable. Returns False if none are left."""
        if self.kind(iid) != "consumable" or not self.owns(iid):
            return False
        self.rows[iid]["uses"] -= 1
        if self.rows[iid]["uses"] <= 0:
            del self.rows[iid]
        return True

    def loadout(self) -> dict[str, bool]:
        """Passive effects to pass into a mission context."""
        eq = set(self.equipped())
        return {"ghost_proxy": "ghost_proxy" in eq, "neural": "neural_accelerator" in eq,
                "signal_mask": "signal_mask" in eq}

    def to_rows(self) -> dict[str, dict[str, int]]:
        """Copy of the rows for saving."""
        return {k: dict(v) for k, v in self.rows.items()}
