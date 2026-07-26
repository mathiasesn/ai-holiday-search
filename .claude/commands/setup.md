---
description: Onboard a traveler profile from documents, a pasted description, or an interview
argument-hint: "[optional: paste a freeform description of your travel preferences]"
allowed-tools: Read, Write, Glob, Bash(mkdir:*)
---

# /setup — Build the traveler profile

## Purpose
Populate the local, gitignored `profile/` folder (`01-traveler-profile.md` … `06-packing-and-prep.md`)
and `trip_tracker.csv` from the framework templates in `.claude/skills/holiday-planner/`, so
`/scrape` and `/plan` have a real profile to evaluate trips against. Also seeds
`profile/tooling.md`, the browser-driver preference (see step 6 for what that is and isn't).

## Inputs
- `$ARGUMENTS` — optional. If present, treat it as a pasted freeform description (mode b).
- `documents/` folder — may contain `past-trips/` and `preferences/` material (mode a).
- Existing `profile/` files — if present, this run is an update, not a first fill.
- Existing `profile/tooling.md` — if present, this run must not silently overwrite it.

## State touched
- Reads (never writes): `.claude/skills/holiday-planner/01-traveler-profile.md` … `06-packing-and-prep.md` (templates with `<!-- FILL IN -->` markers).
- Writes: `profile/01-traveler-profile.md` … `profile/06-packing-and-prep.md`.
- Writes: `profile/tooling.md` (browser-driver preference; see step 6) if it does not already exist, or after confirming an overwrite with the user if it does.
- Writes: `trip_tracker.csv` (copied from `trip_tracker.csv.example`) if it does not already exist.
- Never touches `documents/`, `.claude/skills/`, or any tracked framework file.

## Steps

1. **Detect available modes.**
   - Check whether `documents/past-trips/` or `documents/preferences/` contains any files besides their own `README.md`. If yes, mode (a) is available.
   - Check whether `$ARGUMENTS` is non-empty. If yes, mode (b) is available.
   - Mode (c), the interview, is always available.
   - If more than one mode is available, **ask the user which to use** (or whether to combine them, e.g. read documents first, then interview to fill gaps). Do not silently pick one.
   - If `profile/` already contains filled files, tell the user this looks like an update and ask whether to merge new input into the existing profile or start over (starting over should point them at `/reset profile` first, then re-run `/setup`).

2. **Mode (a): read `documents/`.**
   - Read every file under `documents/past-trips/` and `documents/preferences/` (skip their `README.md` placeholders).
   - Extract: group composition, home airports, budget signals, past destinations with stated opinions (loved/hated and why), style signals, dealbreakers.
   - This mode must be **idempotent**: re-running it after new documents are added should merge new information into the existing `profile/` files rather than duplicating or contradicting prior entries. If new material conflicts with an existing profile statement, surface the conflict to the user and ask which should win.

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

6. **Write profile files.**
   - For each of `01-traveler-profile.md`, `02-travel-style.md`, `03-trip-evaluation.md`, `04-itinerary-templates.md`, `05-budget-rules.md`, `06-packing-and-prep.md`:
     - Read the template from `.claude/skills/holiday-planner/<name>.md`.
     - Replace every `<!-- FILL IN -->` marker with the corresponding captured information. Leave the surrounding structure and framework rules in the template intact — only fill markers, don't rewrite the scaffold.
     - Write the result to `profile/<name>.md`, creating the `profile/` directory first if needed.
   - If `trip_tracker.csv` does not already exist at the repo root, copy `trip_tracker.csv.example` to `trip_tracker.csv` unmodified (header row only).
   - **Seed `profile/tooling.md`** — the browser-driver preference, documented in `ARCHI.md`. This is not one of the six numbered traveler-preference templates and must never be merged into them; it holds a tooling knob, not travel data.
     - If `profile/tooling.md` does not exist, write it with the caller defaults: `/scrape` → `claude-in-chrome`, `/watch` → Playwright MCP.
     - If it already exists, treat this the same as an existing filled profile elsewhere in this flow: do not clobber it silently. Tell the user it already has driver preferences set and ask whether to keep it as-is or reset it to the caller defaults.

7. **State the privacy boundary.** Tell the user explicitly: `profile/` and `trip_tracker.csv` are gitignored and must never be committed to the fork. `profile/01…06-*.md` hold their personal travel data; `profile/tooling.md` holds no travel data at all — it's a local tooling knob (which MCP driver runs browser reads) — but it lives in the same gitignored `profile/` folder and stays local for the same reason: nothing under `profile/` should end up in a shared fork or PR.

8. **Echo a summary for confirmation.** Print a short recap of the captured profile — group composition, home airports, budget range, style, top dealbreakers, and 2-3 history highlights with their stated opinions — and ask the user to confirm it's accurate or point out corrections. Do not treat the profile as final until confirmed; re-write the affected file(s) if the user corrects something.

## Output
A confirmed, filled `profile/` folder (including `tooling.md`) ready for `/scrape` and `/plan`, plus `trip_tracker.csv` if it was missing.
