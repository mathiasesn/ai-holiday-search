---
description: Save trips to a price watchlist and re-check them for price drops, rises, or sold-out status
argument-hint: "add <trip> | remove <trip> | (no args: re-check all watched trips)"
allowed-tools: Read, Write, Bash, Glob, WebSearch, WebFetch, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__find, mcp__claude-in-chrome__form_input, mcp__playwright__browser_tabs, mcp__playwright__browser_navigate, mcp__playwright__browser_fill_form, mcp__playwright__browser_type, mcp__playwright__browser_click, mcp__playwright__browser_select_option, mcp__playwright__browser_press_key, mcp__playwright__browser_find, mcp__playwright__browser_snapshot, mcp__playwright__browser_wait_for, mcp__playwright__browser_console_messages, mcp__playwright__browser_take_screenshot
---

# /watch — Price tracking

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
Snapshot trips found via `/scrape` or `/plan` into a local watchlist, then re-check them on demand
(or on a schedule) to report price drops, rises, and sold-out warnings.

## Inputs
- `$ARGUMENTS` — one of:
  - `add <trip>` — snapshot a trip (by name/slug, or referring to the most recent `/scrape`/`/plan` result) into the watchlist.
  - `remove <trip>` — remove a trip from the watchlist.
  - *(empty)* — re-check every trip currently in the watchlist.
- `<DATA_ROOT>/watchlist/<slug>.json` — one file per watched trip; see shape below.
- `<DATA_ROOT>/profile/tooling.md` — optional. Holds the browser-driver preference for this run. If absent, or present but missing the `/watch` driver field, default to Playwright MCP.
- [../skills/price-watch/SKILL.md](../skills/price-watch/SKILL.md) — authoritative definition of the JSON shape and re-check logic; defer to it for any detail not covered here.
- `<FRAMEWORK_ROOT>/.agents/skills/{flights-search,stays-search,packages-search}/search.py` — used to re-search the same route/dates on re-check for adapter-backed trips.
- [../skills/trivago-search/SKILL.md](../skills/trivago-search/SKILL.md) — authoritative driver contract (server config, tool-capability mapping, etiquette limits) for re-checking browser-driven trips (`trivago-search`, `momondo-search`, `booking-search`); re-check dispatches to it rather than restating it here.

## State touched
- Reads/writes: `<DATA_ROOT>/watchlist/<slug>.json` (one per trip; created, updated, or deleted).
- Never touches `<DATA_ROOT>/profile/` or `<DATA_ROOT>/trip_scraper/`.

## Before anything else
If this run needs profile data (e.g. resolving `<trip>` against profile-derived context, or any currency/preference defaults), check `<DATA_ROOT>/profile/` first. If `<DATA_ROOT>/profile/` doesn't exist or any file still contains `<!-- FILL IN -->` markers, stop and tell the user to run `/setup` first — do not proceed with a partial profile.

`<DATA_ROOT>/profile/tooling.md` (driver preference) is exempt from that check: if it's absent, or present but missing the relevant field, do not stop or prompt `/setup` — the caller default (Playwright MCP) applies silently. An existing `<DATA_ROOT>/profile/` predating this file must keep working with no migration.

## Steps

0. **Resolve the browser driver.** Read `<DATA_ROOT>/profile/tooling.md` if it exists, mirroring `/scrape`'s step 0. If the file or its `/watch` driver field is absent, use the default Playwright MCP; if present, honor whatever it specifies (`claude-in-chrome` or Playwright MCP). This absence is normal and silent — never an error, never the "run `/setup`" precondition above.

## Subcommands

### `/watch add <trip>`
1. Identify the trip: use `<trip>` to match a recent `/scrape` result or the destination/dates from a just-completed `/plan` run. If ambiguous, ask the user which trip they mean.
2. Derive the slug per [../skills/price-watch/SKILL.md](../skills/price-watch/SKILL.md) — the authoritative source for slug derivation.
3. Read [../skills/price-watch/SKILL.md](../skills/price-watch/SKILL.md) for the exact JSON shape expected in `<DATA_ROOT>/watchlist/<slug>.json` and follow it precisely.
4. Write `<DATA_ROOT>/watchlist/<slug>.json`. If a file for that slug already exists, ask before overwriting.
5. Confirm to the user what was saved and under which slug.

### `/watch remove <trip>`
1. Resolve `<trip>` to a slug in `<DATA_ROOT>/watchlist/`. If no exact match, list close matches and ask the user to disambiguate.
2. Delete `<DATA_ROOT>/watchlist/<slug>.json`.
3. Confirm removal.

### `/watch` (no arguments — re-check all)
1. List every `<DATA_ROOT>/watchlist/*.json` file. If none exist, tell the user the watchlist is empty and suggest `/watch add <trip>` after a `/scrape` or `/plan` run.
2. For each watched trip, dispatch on `trip.source` into one of three branches — adapter-backed, browser-driven, or pasted — per [../skills/price-watch/SKILL.md](../skills/price-watch/SKILL.md) "Re-check procedure", the sole authority for this logic; do not re-enumerate the triggers or branches here.
   - Compare the new price against the most recent entry in the trip's price history.
   - Classify the result: price drop, price rise, unchanged, sold-out/unavailable, or blocked read.
   - Append the new observation (timestamp, price, currency, availability) to the trip's price history array in `<DATA_ROOT>/watchlist/<slug>.json`. The entry shape and `schema_version: 1` are unchanged, and entries never record which driver produced them.
3. Report a summary table across all watched trips: destination, dates, previous price, current price, delta, and status (drop / rise / unchanged / sold out / blocked read).
4. Highlight drops and sold-out warnings first — these are the actionable items. Report blocked reads separately from sold-out warnings; do not let a run with several blocked browser-driven trips read as mass sold-out.

## Notes on uncertainty
Re-checked prices are frequently not confirmed by a live authoritative source (a stale adapter
response, a web-search result, or a browser read that got partial data) — this applies to both
the adapter-backed and pasted branches. Any such figure, and any delta computed from it, must be
labeled as an estimate to verify at booking — never present a guess as a confirmed fact.

## Scheduling
`/watch` (no args) is idempotent, and both adapter-backed and browser-driven trips can now run unattended. Neither an unattended scheduled run nor a manual attended one has yet been exercised against the real sites — verify the first few scheduled runs manually before relying on them. See [../skills/price-watch/SKILL.md](../skills/price-watch/SKILL.md) "Scheduling" and [../ARCHI.md](../ARCHI.md) §7 for the driver rationale and server config.

## Output
Updated `<DATA_ROOT>/watchlist/<slug>.json` file(s) with appended price history, and a human-readable price-change report on each `/watch` (no-args) run.
