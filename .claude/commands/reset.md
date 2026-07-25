---
description: Destructively clear local profile, watchlist, or all generated state (requires typing RESET to confirm)
argument-hint: "profile | watchlist | all"
allowed-tools: Read, Bash(rm:*), Glob
---

# /reset — Wipe local generated/personal state

## Purpose
Let the user start over by clearing gitignored, personal/generated data, without ever touching
tracked framework files (templates, skills, commands, tooling). This command is destructive and
must never act without explicit, exact confirmation.

## Inputs
- `$ARGUMENTS` — required, one of `profile`, `watchlist`, `all`. If missing or not one of these three, stop and ask the user which they mean — do not guess or default.

## What each mode deletes

### `profile`
- Deletes: `profile/` (the entire directory — `01-traveler-profile.md` … `06-packing-and-prep.md` and anything else under it) and `trip_tracker.csv`.
- **Preserves**: the tracked templates in `.claude/skills/holiday-planner/*.md` (the `<!-- FILL IN -->` scaffolds), `trip_tracker.csv.example`, and all other framework rules/commands/skills.
- After this, the user must run `/setup` again before `/scrape` or `/plan` will work.

### `watchlist`
- Deletes: `watchlist/` (all `watchlist/<slug>.json` files and any price history they contain).
- Preserves: `.claude/skills/price-watch/SKILL.md` and everything else.

### `all`
- Does everything `profile` and `watchlist` do, **plus**:
- Deletes: `trip_scraper/` state (`trip_scraper/seen.json` and any results snapshots).
- Preserves: all tracked framework files, `.agents/skills/*`, `documents/README.md` (the folder layout instructions), and `documents/past-trips/`, `documents/preferences/` themselves are NOT deleted by `/reset all` unless the user separately asks — this command only clears profile/watchlist/scraper state, not source documents. State this explicitly to the user.

## Steps

1. Parse `$ARGUMENTS`. If it isn't exactly `profile`, `watchlist`, or `all`, ask the user to specify one of the three and stop.
2. **Enumerate the exact files/directories that will be deleted** for the requested mode, using the lists above — check what actually exists on disk (e.g. `ls profile/ watchlist/ trip_scraper/` / `find` as appropriate) and print the real, concrete file paths, not just the category. If a target directory doesn't exist or is already empty, say so (nothing to delete there).
3. State clearly what is **preserved** (the relevant bullet list above), so the user knows framework/tracked files are safe.
4. Ask the user to **type `RESET` verbatim** to confirm. Do not proceed on "yes", "y", "confirm", or any other input — only the exact string `RESET` (case-sensitive) authorizes deletion. Any other response aborts with no changes made.
5. On confirmation, delete exactly the enumerated files/directories from step 2 — nothing more. Never delete anything under `.claude/`, `.agents/skills/`, `documents/README.md`, `tools/`, `.github/`, or any other tracked framework path.
6. Report what was actually deleted, and remind the user of the preserved items and, for `profile`/`all`, that `/setup` is needed again before searching or planning.

## Output
Confirmed deletion of exactly the requested local state, with an explicit before-action file list and an after-action confirmation. No tracked framework file is ever touched.
