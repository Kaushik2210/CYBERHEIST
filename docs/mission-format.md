# Mission file format

Campaign missions are plain [TOML](https://toml.io) files, one mission per file. You can
write them without touching any Python.

The game loads them from two folders, in this order:

1. `missions/campaign/` in the game itself (missions that ship with the game)
2. `~/.cyberheist/missions/` (your own missions)

Files are read in name order, so `01-first.toml`, `02-second.toml` and so on works well.
If `missions/mission_data.py` exists it takes priority and the files are not read.

Start from [examples/example-mission.toml](examples/example-mission.toml).

## Check your missions

```
cyberheist --check-missions              # both folders above
cyberheist --check-missions path/to/dir  # one folder
```

This reports every problem in every file, then plays each valid mission with the
logic-perfect autopilot on five seeds for each difficulty. A mission the autopilot can't
clear on Easy is marked **TOO HARD**, which usually means the tick budget is too small.
The command exits with 1 if anything is wrong, so you can use it in CI.

Bad files never crash the game. They are left out, and the mission database says how
many problems it found.

## Top-level keys

| Key | Type | Meaning |
|---|---|---|
| `id` | integer | Mission number. Ids should run 1, 2, 3… without gaps. Mission 1 starts unlocked; each clear unlocks the next. |
| `title` | text | Shown in the database and briefing. |
| `tier` | text | A short label, such as `Training` or `Corporate`. |
| `intro` | text | One or two lines of story shown above the briefing. |
| `briefing` | text | What the player has to do. |
| `primary` | list of text | Objectives listed in the briefing. |
| `completion` | text | Shown after a clear. |
| `par_ticks` | integer | Target time. Finishing under it pays a speed bonus. |
| `grace_ticks` | integer | After this many ticks, each tick adds detection. |
| `max_ticks` | integer | Hard limit: the mission fails here. Must be `par ≤ grace ≤ max`. |
| `reward_xp`, `reward_credits` | integer | Base rewards for a clear. |
| `events` | true/false | Random events during the run. Optional, default `true`. |
| `failure` | list of text | Failure conditions listed in the briefing. Optional. |

## Stages

Each `[[stages]]` table is one stage, played in order. Every stage has a `type`, an
optional `label`, and optional `params`. Leave a param out to use the default, which also
applies the difficulty setting. Any stage can also take `patrol` (0–5): extra detection
added every tick during that stage.

| `type` | Params (range, default) |
|---|---|
| `shell` | none: the tutorial shell |
| `firewall` | `pool` (4–8, 6), `length` (3–6, 4), `attempts` (1–20, 8), `repeats` (bool), `margin` (0–10) |
| `cipher` | `kind` (**required**: caesar, vigenere, substitution, binary, hex, pattern, layered), `attempts` (1–10, 3), `tough` (bool) |
| `password` | `words` (4–20, 8), `digits` (1–4, 2), `symbols` (2–8, 4), `range` (2–10), `attempts` (1–20, 6), `hide_words`, `sum_clue` (bool), `margin` (0–10) |
| `network` | `target` (DATABASE or BACKUP), `hidden` (0–2, 1), `locks` (0–2), `tough` (bool) |
| `escape` | `rounds` (1–8, 3), `slack` (0–20, 4), `tough` (bool) |

Every lock is still solvable: attempts never drop below what the solver needs.

## Optional objectives

Each `[[optional]]` table pays a bonus when met.

| Key | Meaning |
|---|---|
| `id` | Unique within the mission. Saved with the player's progress, so don't rename it later. |
| `text` | Shown in the briefing. |
| `kind` | `max_ticks` (finish within `value` ticks), `max_detection` (peak detection under `value`), `no_wrong` (at most `value` wrong guesses) or `hidden_node` (find a hidden network node; no `value`). |
| `value` | Number for the kinds above. |
| `xp`, `credits` | Bonus paid. |

## Keep it fictional

Missions are set in an invented world. Use made-up companies, hosts and people, and
don't describe real systems, real tools or real attack steps.
