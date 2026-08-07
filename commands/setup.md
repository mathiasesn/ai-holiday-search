---
description: Onboard a traveler profile from documents, a pasted description, or an interview
argument-hint: "[optional: paste a freeform description of your travel preferences]"
allowed-tools: Read, Write, Glob, Bash(mkdir:*), Bash(test:*)
---

# /setup — Build the traveler profile

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
Populate the `<DATA_ROOT>/profile/` folder (`01-traveler-profile.md` … `06-packing-and-prep.md`)
and `<DATA_ROOT>/trip_tracker.csv` from the framework templates in `<FRAMEWORK_ROOT>/skills/holiday-planner/`, so
`/scrape` and `/plan` have a real profile to evaluate trips against. Also seeds
`<DATA_ROOT>/profile/tooling.md`, the browser-driver preference (see step 7 for what that is and isn't).

## Inputs
- `$ARGUMENTS` — optional. If present, treat it as a pasted freeform description (mode b).
- `<DATA_ROOT>/documents/` folder — may contain past-trips and preferences material in their respective subfolders (mode a). Create those subfolders on demand if missing.
- Existing `<DATA_ROOT>/profile/` files — if present, this run is an update, not a first fill.
- Existing `<DATA_ROOT>/profile/tooling.md` — if present, this run must not silently overwrite it.

## State touched
- Reads (never writes): `<FRAMEWORK_ROOT>/skills/holiday-planner/01-traveler-profile.md` … `06-packing-and-prep.md` (templates with `<!-- FILL IN -->` markers).
- Writes: `<DATA_ROOT>/profile/01-traveler-profile.md` … `<DATA_ROOT>/profile/06-packing-and-prep.md`.
- Writes: `<DATA_ROOT>/profile/tooling.md` (browser-driver preference; see step 7) if it does not already exist, or after confirming an overwrite with the user if it does.
- Writes: `<DATA_ROOT>/trip_tracker.csv` (copied from `<FRAMEWORK_ROOT>/trip_tracker.csv.example`) if it does not already exist.
- Never touches `<DATA_ROOT>/documents/`, `<FRAMEWORK_ROOT>/skills/`, or any tracked framework file.

## Steps

1. **Detect available modes.**
   - Check whether `<DATA_ROOT>/documents/past-trips/` or `<DATA_ROOT>/documents/preferences/` contains any files besides their own `README.md`. If yes, mode (a) is available.
   - Check whether `$ARGUMENTS` is non-empty. If yes, mode (b) is available.
   - Mode (c), the interview, is always available.
   - If more than one mode is available, **ask the user which to use** (or whether to combine them, e.g. read documents first, then interview to fill gaps). Do not silently pick one.
   - If `<DATA_ROOT>/profile/` already contains filled files, tell the user this looks like an update and ask whether to merge new input into the existing profile or start over (starting over should point them at `/reset profile` first, then re-run `/setup`).

2. **Mode (a): read `<DATA_ROOT>/documents/`.**
   - Read every file under `<DATA_ROOT>/documents/past-trips/` and `<DATA_ROOT>/documents/preferences/` (skip their `README.md` placeholders).
   - Extract: group composition, home airports, budget signals, past destinations with stated opinions (loved/hated and why), style signals, dealbreakers.
   - This mode must be **idempotent**: re-running it after new documents are added should merge new information into the existing `<DATA_ROOT>/profile/` files rather than duplicating or contradicting prior entries. If new material conflicts with an existing profile statement, surface the conflict to the user and ask which should win.

3. **Mode (b): import pasted description.**
   - Parse `$ARGUMENTS` (or, if empty but the user just pasted a description in chat instead of using arguments, use that) for the same categories as mode (a).
   - Explicitly note which of the five interview areas (below) are still unanswered after parsing the paste, and move to a short follow-up interview for just those gaps.

4. **Mode (c): interview.**
   Ask about exactly these five areas, one at a time or grouped, in plain conversational questions. Do not skip any:
   - **Who's traveling** — adults, kids and their ages, pets, mobility constraints.
   - **Constraints** — home airport(s) (e.g. CPH, BLL — examples, use the user's real airports), budget range (state currency; EUR is the framework default, note DKK equivalents if the user is Danish), dates and how flexible they are, max acceptable travel time, visa/passport situation.
   - **Style** — beach vs. city vs. nature vs. ski, pace (packed vs. relaxed), accommodation standard, food priorities.
   - **Dealbreakers and must-haves** — pool, walkability, direct flights only, no hostels, etc.
   - **History with opinions attached** — where they've been, what worked, what didn't. **This is the single highest-value input.** Explicitly tell the user this before asking, and push for specifics: not just "we went to Mallorca" but *why* it worked or didn't (e.g. "loved Ljubljana — walkable, low-key"; "hated the Mallorca resort — trapped without a car"). Ask at least one follow-up if the first answer is a bare list of place names with no opinions.

5. **Merge and normalize.** Combine whatever was gathered from modes (a)/(b)/(c) into a single coherent set of answers covering all five interview areas. Flag any area still missing information and ask a final clarifying question before writing files, rather than guessing.

6. **Ensure `<DATA_ROOT>` is gitignored (plugin mode only).** In plugin mode, before writing
   any profile file, check whether `<DATA_ROOT>/.gitignore` exists by running
   `test -f <DATA_ROOT>/.gitignore` (via the `Bash(test:*)` allowance above — `Glob` typically
   skips dotfiles and `Read` errors on a missing file, so neither gives a clean existence
   check). If the command exits non-zero, create the file containing a single line: `*`. This
   is necessary because `<DATA_ROOT>` is `~/.ai-holiday-search`,
   and `$HOME` may itself be a tracked git repo (e.g. a dotfiles repo) — without this file, personal
   profile data written under `~/.ai-holiday-search` could get swept into a commit there. In clone
   mode, skip this step; `DATA_ROOT` is the repo root, already covered by this repo's own `.gitignore`.

7. **Write profile files.**
   - For each of `01-traveler-profile.md`, `02-travel-style.md`, `03-trip-evaluation.md`, `04-itinerary-templates.md`, `05-budget-rules.md`, `06-packing-and-prep.md`:
     - Read the template from `<FRAMEWORK_ROOT>/skills/holiday-planner/<name>.md`.
     - Replace every `<!-- FILL IN -->` marker with the corresponding captured information. Leave the surrounding structure and framework rules in the template intact — only fill markers, don't rewrite the scaffold.
     - Write the result to `<DATA_ROOT>/profile/<name>.md`, creating the `<DATA_ROOT>/profile/` directory first if needed.
   - If `<DATA_ROOT>/trip_tracker.csv` does not already exist, copy `<FRAMEWORK_ROOT>/trip_tracker.csv.example` to `<DATA_ROOT>/trip_tracker.csv` unmodified (header row only).
   - **Seed `<DATA_ROOT>/profile/tooling.md`** — the browser-driver preference, documented in [../ARCHI.md](../ARCHI.md). This is not one of the six numbered traveler-preference templates and must never be merged into them; it holds a tooling knob, not travel data.
     - If `<DATA_ROOT>/profile/tooling.md` does not exist, write it with the caller defaults: `/scrape` → `claude-in-chrome`, `/watch` → Playwright MCP.
     - If it already exists, treat this the same as an existing filled profile elsewhere in this flow: do not clobber it silently. Tell the user it already has driver preferences set and ask whether to keep it as-is or reset it to the caller defaults.

8. **State the privacy boundary.** Tell the user explicitly: `<DATA_ROOT>/profile/` and `<DATA_ROOT>/trip_tracker.csv` are personal data and must never be committed anywhere — in plugin mode they live outside any repo (under `~/.ai-holiday-search`, protected by the `<DATA_ROOT>/.gitignore` created in step 6 in case `$HOME` is itself a tracked repo), and in clone mode they are gitignored. The six numbered files hold their personal travel data; `tooling.md` holds no travel data at all — it's a local tooling knob (which MCP driver runs browser reads) — but it lives alongside them and stays local for the same reason: nothing under `<DATA_ROOT>/profile/` should end up in a shared fork or PR. Report `<DATA_ROOT>`'s absolute path to the user so they know where their local data lives.

9. **Echo a summary for confirmation.** Print a short recap of the captured profile — group composition, home airports, budget range, style, top dealbreakers, and 2-3 history highlights with their stated opinions — and ask the user to confirm it's accurate or point out corrections. Do not treat the profile as final until confirmed; re-write the affected file(s) if the user corrects something.

## Output
A confirmed, filled `<DATA_ROOT>/profile/` folder (including `tooling.md`) ready for `/scrape` and `/plan`, plus `<DATA_ROOT>/trip_tracker.csv` if it was missing.
