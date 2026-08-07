---
description: Destructively clear local profile, watchlist, or all generated state (requires typing RESET to confirm)
argument-hint: "profile | watchlist | all"
allowed-tools: Read, Glob, Bash(ls:*), Bash(rm:*)
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

**Fallback if `${CLAUDE_PLUGIN_ROOT}` fails to resolve.** If a path containing
`${CLAUDE_PLUGIN_ROOT}` does not actually resolve (the variable was not interpolated), do not
silently fall back to the current working directory. Instead, determine `FRAMEWORK_ROOT` by
locating the directory that contains both `ARCHI.md` and `.agents/skills/` (this will be either
the installed plugin directory or this repo's root). If that directory cannot be found either,
tell the user the framework root could not be resolved and stop — do not read or write any tree
under a guessed root.

## Purpose
Let the user start over by clearing personal/generated data under `DATA_ROOT`. Framework files
(templates, skills, commands, tooling) are never touched — see "Explicit protect-list" below for
the authoritative statement of what that means. This command is destructive and must never act
without explicit, exact confirmation.

For more on the framework's layout and conventions, see [README](../README.md), [SETUP](../SETUP.md),
[ARCHI](../ARCHI.md), and [AGENTS](../AGENTS.md).

## Inputs
- `$ARGUMENTS` — required, one of `profile`, `watchlist`, `all`. If missing or not one of these three, stop and ask the user which they mean — do not guess or default.

## What each mode deletes

All deletions below are scoped to `<DATA_ROOT>` only. See "Explicit protect-list" below for the
authoritative statement of what must never be touched.

### `profile`
- Deletes: `<DATA_ROOT>/profile/` (the entire directory — `01-traveler-profile.md` … `06-packing-and-prep.md` and anything else under it) and `<DATA_ROOT>/trip_tracker.csv`.
- **Preserves**: the tracked templates in `<FRAMEWORK_ROOT>/skills/holiday-planner/*.md` (the `<!-- FILL IN -->` scaffolds), `<FRAMEWORK_ROOT>/trip_tracker.csv.example`, and all other framework rules/commands/skills.
- After this, the user must run `/setup` again before `/scrape` or `/plan` will work.

### `watchlist`
- Deletes: `<DATA_ROOT>/watchlist/` (one JSON file per watched trip, and any price history it contains).
- Preserves: `<FRAMEWORK_ROOT>/skills/price-watch/SKILL.md` and everything else.

### `all`
- Does everything `profile` and `watchlist` do, **plus**:
- Deletes: `<DATA_ROOT>/trip_scraper/` state (the seen-candidates registry and any results snapshots).
- Preserves: all framework/tracked files (see protect-list below), `<DATA_ROOT>/documents/README.md` (the folder layout instructions, if present); `<DATA_ROOT>/documents/past-trips/` and `<DATA_ROOT>/documents/preferences/` themselves are NOT deleted by `/reset all` unless the user separately asks — this command only clears the state covered by the `profile`, `watchlist`, and `all` sections above, not source documents. State this explicitly to the user. Also preserves `<DATA_ROOT>/.gitignore` (written by `/setup` in plugin mode, containing `*`) — deleting it would leave the data root unprotected until the next `/setup` run, so it is kept even under `all`.

## Explicit protect-list (never delete)

These paths are never deletion targets under any mode of this command, regardless of
`$ARGUMENTS` — this is the authoritative statement; every step below and every mode's "preserves"
line refer back to it rather than restating it:

- `<FRAMEWORK_ROOT>/.claude/`
- `<FRAMEWORK_ROOT>/.agents/skills/`
- `<FRAMEWORK_ROOT>/commands/`
- `<FRAMEWORK_ROOT>/skills/`
- `<FRAMEWORK_ROOT>/tools/`
- `<FRAMEWORK_ROOT>/.github/`
- `<FRAMEWORK_ROOT>/.claude-plugin/`
- `<FRAMEWORK_ROOT>/pyproject.toml`
- `<FRAMEWORK_ROOT>/trip_tracker.csv.example`
- `<FRAMEWORK_ROOT>/README.md`, `<FRAMEWORK_ROOT>/SETUP.md`, `<FRAMEWORK_ROOT>/ARCHI.md`, `<FRAMEWORK_ROOT>/AGENTS.md`

**Clone mode makes this list load-bearing, not redundant.** In clone mode `FRAMEWORK_ROOT ==
DATA_ROOT == the repo root`, so "delete only under `<DATA_ROOT>`" is trivially true of every file
in the repo and is **not** sufficient protection on its own — it would equally justify deleting
this list's contents. `/reset` must delete only the specific paths enumerated in "What each mode
deletes" above, never a whole-directory sweep of `<DATA_ROOT>` (or of the repo root when the two
roots coincide), and never anything on this protect-list even when `FRAMEWORK_ROOT` and
`DATA_ROOT` are the same directory. Every deletion step below must be checked against this list
before it runs.

## Steps

1. Parse `$ARGUMENTS`. If it isn't exactly `profile`, `watchlist`, or `all`, ask the user to specify one of the three and stop.
2. **Enumerate the exact files/directories that will be deleted** for the requested mode, using the lists above — check what actually exists on disk under `<DATA_ROOT>` (e.g. `ls -A <DATA_ROOT>/profile/ <DATA_ROOT>/watchlist/ <DATA_ROOT>/trip_scraper/`, or `Glob`) and print the real, concrete absolute file paths, not just the category. Enumerate with read-only tools only — this step's job is to *show* what will be deleted before the user authorizes it, so it must not be able to delete anything itself. If a target directory doesn't exist or is already empty, say so (nothing to delete there).
3. State clearly what is **preserved** (the relevant bullet list above), so the user knows framework/tracked files are safe.
4. Ask the user to **type `RESET` verbatim** to confirm. Do not proceed on "yes", "y", "confirm", or any other input — only the exact string `RESET` (case-sensitive) authorizes deletion. Any other response aborts with no changes made.
5. On confirmation, delete exactly the enumerated files/directories from step 2 — nothing more, respecting the protect-list above.
6. Report what was actually deleted, and remind the user of the preserved items and, for `profile`/`all`, that `/setup` is needed again before searching or planning.

## Output
Confirmed deletion of exactly the requested local state under `<DATA_ROOT>`, with an explicit before-action absolute file list and an after-action confirmation. Framework/tracked files are never touched (see protect-list).
