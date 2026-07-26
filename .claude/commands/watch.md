---
description: Save trips to a price watchlist and re-check them for price drops, rises, or sold-out status
argument-hint: "add <trip> | remove <trip> | (no args: re-check all watched trips)"
allowed-tools: Read, Write, Bash, Glob, WebSearch, WebFetch, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__find, mcp__claude-in-chrome__form_input, mcp__playwright__browser_tabs, mcp__playwright__browser_navigate, mcp__playwright__browser_fill_form, mcp__playwright__browser_type, mcp__playwright__browser_click, mcp__playwright__browser_select_option, mcp__playwright__browser_press_key, mcp__playwright__browser_find, mcp__playwright__browser_snapshot, mcp__playwright__browser_wait_for, mcp__playwright__browser_console_messages, mcp__playwright__browser_take_screenshot
---

# /watch — Price tracking

## Purpose
Snapshot trips found via `/scrape` or `/plan` into a local watchlist, then re-check them on demand
(or on a schedule) to report price drops, rises, and sold-out warnings.

## Inputs
- `$ARGUMENTS` — one of:
  - `add <trip>` — snapshot a trip (by name/slug, or referring to the most recent `/scrape`/`/plan` result) into the watchlist.
  - `remove <trip>` — remove a trip from the watchlist.
  - *(empty)* — re-check every trip currently in the watchlist.
- `watchlist/<slug>.json` — one file per watched trip; see shape below.
- `profile/tooling.md` — optional. Holds the browser-driver preference for this run. If absent, or present but missing the `/watch` driver field, default to Playwright MCP.
- `.claude/skills/price-watch/SKILL.md` — authoritative definition of the JSON shape and re-check logic; defer to it for any detail not covered here.
- `.agents/skills/{flights-search,stays-search,packages-search}/search.py` — used to re-search the same route/dates on re-check for adapter-backed trips.
- `.claude/skills/trivago-search/SKILL.md` — authoritative driver contract (server config, tool-capability mapping, etiquette limits) for re-checking browser-driven trips (`trivago-search`, `momondo-search`, `booking-search`); re-check dispatches to it rather than restating it here.

## State touched
- Reads/writes: `watchlist/<slug>.json` (one per trip; created, updated, or deleted).
- Never touches `profile/` or `trip_scraper/`.

## Before anything else
If this run needs profile data (e.g. resolving `<trip>` against profile-derived context, or any currency/preference defaults), check `profile/` first. If `profile/` doesn't exist or any file still contains `<!-- FILL IN -->` markers, stop and tell the user to run `/setup` first — do not proceed with a partial profile.

`profile/tooling.md` (driver preference) is exempt from that check: if it's absent, or present but missing the relevant field, do not stop or prompt `/setup` — the caller default (Playwright MCP) applies silently. An existing `profile/` predating this file must keep working with no migration.

## Steps

0. **Resolve the browser driver.** Read `profile/tooling.md` if it exists, mirroring `/scrape`'s step 0. If the file or its `/watch` driver field is absent, use the default Playwright MCP; if present, honor whatever it specifies (`claude-in-chrome` or Playwright MCP). This absence is normal and silent — never an error, never the "run `/setup`" precondition above.

## Subcommands

### `/watch add <trip>`
1. Identify the trip: use `<trip>` to match a recent `/scrape` result or the destination/dates from a just-completed `/plan` run. If ambiguous, ask the user which trip they mean.
2. Derive the slug per `.claude/skills/price-watch/SKILL.md` — the authoritative source for slug derivation.
3. Read `.claude/skills/price-watch/SKILL.md` for the exact JSON shape expected in `watchlist/<slug>.json` and follow it precisely.
4. Write `watchlist/<slug>.json`. If a file for that slug already exists, ask before overwriting.
5. Confirm to the user what was saved and under which slug.

### `/watch remove <trip>`
1. Resolve `<trip>` to a slug in `watchlist/`. If no exact match, list close matches and ask the user to disambiguate.
2. Delete `watchlist/<slug>.json`.
3. Confirm removal.

### `/watch` (no arguments — re-check all)
1. List every `watchlist/*.json` file. If none exist, tell the user the watchlist is empty and suggest `/watch add <trip>` after a `/scrape` or `/plan` run.
2. For each watched trip, dispatch on `trip.source` into one of three branches — adapter-backed, browser-driven, or pasted — per `.claude/skills/price-watch/SKILL.md` "Re-check procedure", the sole authority for this logic; do not re-enumerate the triggers or branches here.
   - Compare the new price against the most recent entry in the trip's price history.
   - Classify the result: price drop, price rise, unchanged, sold-out/unavailable, or blocked read.
   - Append the new observation (timestamp, price, currency, availability) to the trip's price history array in `watchlist/<slug>.json`. The entry shape and `schema_version: 1` are unchanged, and entries never record which driver produced them.
3. Report a summary table across all watched trips: destination, dates, previous price, current price, delta, and status (drop / rise / unchanged / sold out / blocked read).
4. Highlight drops and sold-out warnings first — these are the actionable items. Report blocked reads separately from sold-out warnings; do not let a run with several blocked browser-driven trips read as mass sold-out.

## Scheduling
`/watch` (no args) is idempotent, and both adapter-backed and browser-driven trips can now run unattended. Neither an unattended scheduled run nor a manual attended one has yet been exercised against the real sites — verify the first few scheduled runs manually before relying on them. See `.claude/skills/price-watch/SKILL.md` "Scheduling" and `ARCHI.md` §7 for the driver rationale and server config.

## Output
Updated `watchlist/<slug>.json` file(s) with appended price history, and a human-readable price-change report on each `/watch` (no-args) run.
