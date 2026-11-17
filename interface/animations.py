"""Short animations. Everything is skipped when the animation setting is off."""
from __future__ import annotations

from interface.ui import UI

BOOT_LINES = [
    "Loading kernel modules", "Mounting virtual filesystems", "Spinning up sandbox network",
    "Calibrating detection meter", "Decrypting operator profile",
]


def boot_sequence(ui: UI, seconds: float = 3.0) -> None:
    """Fake system start-up. Total runtime stays under ``seconds`` at speed 1.0."""
    if not ui.animations:
        return
    step = max(0.05, seconds / (len(BOOT_LINES) * 2 + 4))
    ui.say("CYBERHEIST BIOS v2.077", "dim")
    for line in BOOT_LINES:
        ui.say(f"  {line}...", "dim")
        ui.pause(step)
        ui.say("  " + ui.paint("[ OK ]", "ok"))
        ui.pause(step)
    for pct in (25, 50, 75, 100):
        ui.say(f"  {ui.bar(pct, 100, 30)} {pct:3d}%")
        ui.pause(step)
    ui.blank()


def progress(ui: UI, label: str, steps: int = 4, seconds: float = 0.4) -> None:
    """A small progress bar for transitions."""
    if not ui.animations:
        return
    for i in range(1, steps + 1):
        ui.say(f"{label} {ui.bar(i, steps, 20)}")
        ui.pause(seconds / steps)
