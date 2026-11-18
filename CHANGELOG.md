# Changelog

All notable changes to CYBERHEIST are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-11-18

### Added
- **Mission files:** write campaign missions as TOML files in `cyberheist/missions/campaign/` or
  `~/.cyberheist/missions/`. See `docs/mission-format.md` and the example mission.
- **`--check-missions`:** reports every problem in every mission file, then playtests
  each mission with the autopilot on all three difficulties. Exits with 1 on problems.
- Bad mission files are skipped and counted in the mission database instead of
  stopping the game.
- **Run debrief:** after each stage, a report of ticks, detection and wrong guesses, how
  your probes compared with the solver's par, the exact guess that contradicted an
  earlier clue, and one tip. Runs with several stages end with a summary table and
  the biggest detection leak. A new Debrief setting turns it off.
- Screenshot of the debrief (`docs/screenshots/12-debrief.svg`).

### Changed
- **One package:** all modules now live under a single `cyberheist` package, so
  installing the game no longer adds generic top-level modules like `core` or
  `config`. Run it with `cyberheist` or `python -m cyberheist`. Any custom
  `mission_data.py` imports need the `cyberheist.` prefix.
- **PyPI:** a release workflow publishes tagged versions to PyPI with trusted
  publishing (`pipx install cyberheist`). CI now builds the wheel, checks it with
  twine, and runs the installed command on every OS.

## [0.1.0] - 2026-11-18

First public release. The engine, every challenge type except data extraction, all
game systems and the full menu are complete. The ten-mission campaign is not included
yet. The daily challenge is the complete game loop for now.

### Added
- **Game loop:** boot sequence, CYBERHEIST logo with ASCII fallback, alias
  registration, and the 01–08 main menu (new game, continue, mission database, black
  market, profile, achievements, settings, exit).
- **Challenges**, each solvable on 500 seeds and tougher on Normal and Hard:
  - **Network mapping:** layer-by-layer scans, hidden nodes and route risk ratings.
    Scans cost detection, and the safest route is behind a locked node.
  - **Firewall:** a Mastermind-style rule chain. Attempts are the solver's par plus a
    margin, and Hard allows repeated rules.
  - **Cipher lab:** Caesar, Vigenère, substitution, binary, hex, pattern locks and a
    layered hex-over-Caesar cipher. The Vigenère key is hidden, and lab tools cost
    detection.
  - **Password:** pattern clues with per-position feedback, a digit-sum clue, and a
    hidden word list on Hard.
  - **Escape:** memory, sequence and clue rounds against a tick countdown.
  - **Tutorial shell:** help, scan, connect, ls, cat and status.
- **Systems:** tick clock, detection meter, black market with seven items and a
  two-slot equip limit, seven seeded random events, seven achievements and a statistics
  dashboard.
- **Replay:** a daily challenge seeded by date and puzzle version, a best score per
  day and difficulty, and an adaptive difficulty setting.
- **Careful probes:** a wrong guess that fits every clue so far costs half detection.
- **Saves:** SQLite with migrations (schema v3), integrity and range checks,
  quarantine of corrupt files, checkpoints between stages, and saving on Ctrl+C.
- **Options:** `--seed`, `--reset-save`, `--save-path` and `--version`; green, amber
  and cyan themes; `NO_COLOR` support; an optional terminal bell.
- **Install:** `pipx install` provides a `cyberheist` command.
- **Project:** MIT license, contributing guide, 11 screenshots taken from real runs, and
  CI on Windows, Linux and macOS with Python 3.11–3.13.

### Known gaps
- The ten campaign missions are not written.
- The data-extraction challenge (`challenges/extraction.py`) is not written.

[0.2.0]: https://github.com/Kaushik2210/CYBERHEIST/releases/tag/v0.2.0
[0.1.0]: https://github.com/Kaushik2210/CYBERHEIST/releases/tag/v0.1.0
