---
description: Destructively clear local profile, watchlist, or all generated state (requires typing RESET to confirm)
argument-hint: "profile | watchlist | all"
allowed-tools: Read, Bash(rm:*), Glob
---

# /reset — Wipe local generated/personal state

## Path resolution (framework root and data root)

This framework runs in one of two modes. Resolve every path below through this rule and
never hardcode a repo-relative path:

- **Plugin mode** — `${CLAUDE_PLUGIN_ROOT}` is set (installed via `/plugin install`):
  - `FRAMEWORK_ROOT` = `${CLAUDE_PLUGIN_ROOT}` — adapters, skills, reference files
  - `DATA_ROOT` = `~/.ai-holiday-search` — `profile/`, `itineraries/`, `watchlist/`,
    `trip_scraper/`, `trip_tracker.csv`, `documents/`. Created on demand. Never write
    personal data inside the user's project.
- **Clone mode** — `${CLAUDE_PLUGIN_ROOT}` is unset (this repo is the working directory):
  - `FRAMEWORK_ROOT` = the repo root
  - `DATA_ROOT` = the repo root — today's behavior, covered by the repo's `.gitignore`

Always report a path under `DATA_ROOT` to the user as an absolute path, since in plugin
mode it lies outside the current project.

## Purpose
Let the user start over by clearing personal/generated data under `DATA_ROOT`, without ever
touching `FRAMEWORK_ROOT` (templates, skills, commands, tooling) or anything else in the user's
project. This command is destructive and must never act without explicit, exact confirmation.

## Inputs
- `$ARGUMENTS` — required, one of `profile`, `watchlist`, `all`. If missing or not one of these three, stop and ask the user which they mean — do not guess or default.

## What each mode deletes

All deletions below are scoped to `<DATA_ROOT>` only — never `<FRAMEWORK_ROOT>`, never any
other path in the user's project.

### `profile`
- Deletes: `<DATA_ROOT>/profile/` (the entire directory — `01-traveler-profile.md` … `06-packing-and-prep.md` and anything else under it) and `<DATA_ROOT>/trip_tracker.csv`.
- **Preserves**: the tracked templates in `<FRAMEWORK_ROOT>/skills/holiday-planner/*.md` (the `<!-- FILL IN -->` scaffolds), `trip_tracker.csv.example`, and all other framework rules/commands/skills.
- After this, the user must run `/setup` again before `/scrape` or `/plan` will work.

### `watchlist`
- Deletes: `<DATA_ROOT>/watchlist/` (all `watchlist/<slug>.json` files and any price history they contain).
- Preserves: `<FRAMEWORK_ROOT>/skills/price-watch/SKILL.md` and everything else.

### `all`
- Does everything `profile` and `watchlist` do, **plus**:
- Deletes: `<DATA_ROOT>/trip_scraper/` state (`trip_scraper/seen.json` and any results snapshots).
- Preserves: all of `<FRAMEWORK_ROOT>` (including `.agents/skills/*`), `<DATA_ROOT>/documents/README.md` (the folder layout instructions), and `<DATA_ROOT>/documents/past-trips/`, `<DATA_ROOT>/documents/preferences/` themselves are NOT deleted by `/reset all` unless the user separately asks — this command only clears profile/watchlist/scraper state, not source documents. State this explicitly to the user.

## Steps

1. Parse `$ARGUMENTS`. If it isn't exactly `profile`, `watchlist`, or `all`, ask the user to specify one of the three and stop.
2. **Enumerate the exact files/directories that will be deleted** for the requested mode, using the lists above — check what actually exists on disk under `<DATA_ROOT>` (e.g. `ls <DATA_ROOT>/profile/ <DATA_ROOT>/watchlist/ <DATA_ROOT>/trip_scraper/` / `find` as appropriate) and print the real, concrete absolute file paths, not just the category. If a target directory doesn't exist or is already empty, say so (nothing to delete there).
3. State clearly what is **preserved** (the relevant bullet list above), so the user knows framework/tracked files are safe.
4. Ask the user to **type `RESET` verbatim** to confirm. Do not proceed on "yes", "y", "confirm", or any other input — only the exact string `RESET` (case-sensitive) authorizes deletion. Any other response aborts with no changes made.
5. On confirmation, delete exactly the enumerated files/directories from step 2 — nothing more. Never delete anything under `<FRAMEWORK_ROOT>` (the commands/skills/adapters/tooling tree, however it's mounted in this project) — deletion targets must always resolve under `<DATA_ROOT>`.
6. Report what was actually deleted, and remind the user of the preserved items and, for `profile`/`all`, that `/setup` is needed again before searching or planning.

## Output
Confirmed deletion of exactly the requested local state under `<DATA_ROOT>`, with an explicit before-action absolute file list and an after-action confirmation. No `<FRAMEWORK_ROOT>` file is ever touched.
