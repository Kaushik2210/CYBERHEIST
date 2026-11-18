"""CYBERHEIST: THE TERMINAL BREAK-IN. Entry point.

Usage: python main.py [--seed N] [--reset-save] [--save-path PATH] [--version]
   or: cyberheist [same flags]   (after installing with pipx or pip)
"""
from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from types import FrameType

from core import __version__
from core.game import Game
from database.database import SaveManager
from interface.theme import enable_ansi
from interface.ui import ConsoleIO

DEFAULT_SAVE = Path.home() / ".cyberheist" / "save.db"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line flags."""
    ap = argparse.ArgumentParser(prog="cyberheist", description="CYBERHEIST: THE TERMINAL BREAK-IN")
    ap.add_argument("--version", action="version", version=f"cyberheist {__version__}")
    ap.add_argument("--seed", type=int, default=None, help="seed for a reproducible run (quote it in bug reports)")
    ap.add_argument("--reset-save", action="store_true",
                    help="move the current save aside (save.reset-<timestamp>.db) and start fresh")
    ap.add_argument("--save-path", type=Path, default=DEFAULT_SAVE, help=f"save file (default {DEFAULT_SAVE})")
    return ap.parse_args(argv)


def _on_sigint(signum: int, frame: FrameType | None) -> None:
    """Turn Ctrl+C into KeyboardInterrupt so Game.run saves before exiting.

    Open SQLite transactions roll back on the way out, so the save stays consistent.
    """
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    """Run the game. Returns the process exit code."""
    args = parse_args(argv)
    enable_ansi()
    if args.reset_save:
        sm = SaveManager(args.save_path)
        backup = sm.reset_file()
        sm.close()
        print(f"Save reset. Old save kept as {backup}." if backup else "Save reset (there was no previous save).")
    signal.signal(signal.SIGINT, _on_sigint)
    game = Game(ConsoleIO(), args.save_path, seed=args.seed)
    game.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
