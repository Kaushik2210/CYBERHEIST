# Contributing to CYBERHEIST

Thanks for your interest in improving the game. This guide covers how to set up, the
rules the codebase follows, and how to get a change merged.

## Good places to start

The two biggest open pieces are:

- **The campaign** (`missions/mission_data.py`): ten missions defined as data. The
  runner, briefing screen, rewards and unlock order are already in place. See
  [Adding the campaign](README.md#adding-the-campaign) for the format.
- **Data extraction** (`challenges/extraction.py`): the file-extraction challenge
  described in the README. Missions 4, 5, 8 and 10 need it. The Data Scanner currently
  reveals hidden network nodes and should also reveal hidden files once this exists.

Bug fixes, balance tweaks in `config/settings.json`, and accessibility or layout
improvements are welcome too. For anything large, open an issue first so we can agree
on the approach before you write a lot of code.

## Setup

```bash
git clone https://github.com/Kaushik2210/CYBERHEIST.git
```
```bash
cd CYBERHEIST
```
```bash
python -m venv .venv
```

Activate it with `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on
Linux and macOS, then:

```bash
pip install -r requirements-dev.txt
```
```bash
python -m pytest -q
```

Use a throwaway save while testing so you don't touch your real profile:

```bash
python main.py --save-path test-save.db --seed 42
```

## Ground rules

- **Standard library only at runtime.** pytest is the only dev dependency. Don't add
  packages to `requirements.txt`.
- **Everything stays fictional and local.** No networking, no real tools, commands,
  credentials or targets. Every "network", password and file is generated game data.
- **Python 3.11+, type hints and docstrings** on every public function and class.
- **Never crash on bad input.** Validate what the player types and answer with a
  helpful message.
- **Randomness goes through `core/rng.py`**, so `--seed` keeps runs reproducible. Use
  `rng.fork("label")` for a new subsystem so it doesn't shift other rolls.
- **Balance numbers live in `config/settings.json`**, not in code.
- **Keep the layout within 80×24.** `tests/test_ui.py` checks screen widths.

## Tests

Every change needs tests, and the full suite must pass:

```bash
python -m pytest -q
```

- **New challenge types** must come with a solver and a test that solves at least 500
  seeds, like the existing ones in `tests/test_challenges.py`. A generator should
  guarantee solvability, for example by raising the attempt limit to what its solver
  needed.
- **New stage types** should support the autopilot: pass an `auto=` answer function to
  every prompt so the scripted solver can play them.
- **Menu or flow changes** belong in `tests/test_game.py`, which drives the real game
  loop with scripted input.

CI runs the suite on Windows, Linux and macOS with Python 3.11, 3.12 and 3.13.

- **Changing puzzle generation?** If `test_daily_puzzles_unchanged_for_this_version`
  fails, your change alters the daily runs. Bump `DAILY_VERSION` in `systems/daily.py`
  and add the new fingerprint the test prints. This keeps old and new daily scores apart.

## Screenshots

If you change anything on screen, regenerate the README screenshots and include them
in your pull request:

```bash
python tools/screenshots.py
```

## Commits and pull requests

1. Fork the repo and create a branch from `main`, e.g. `feature/extraction` or
   `fix/hud-width`.
2. Keep each commit focused, with a short message in plain English that says what
   changed: "Add data extraction challenge", "Fix HUD overflow on long objectives".
3. Run the tests before you push.
4. Open a pull request that explains what you changed and why, and how you tested it.
   Link the issue it addresses if there is one.

## Reporting bugs

Open an issue with:

- what you did and what you expected to happen
- what happened instead, including any error message
- your OS, Python version, and the **seed** (shown on the HACKER PROFILE screen, or
  the `--seed` you launched with), so the run can be reproduced

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
