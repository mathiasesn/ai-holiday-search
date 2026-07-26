---
description: Save trips to a price watchlist and re-check them for price drops, rises, or sold-out status
argument-hint: "add <trip> | remove <trip> | (no args: re-check all watched trips)"
allowed-tools: Read, Write, Bash, Glob, WebSearch, WebFetch, mcp__playwright__browser_tabs, mcp__playwright__browser_navigate, mcp__playwright__browser_fill_form, mcp__playwright__browser_type, mcp__playwright__browser_click, mcp__playwright__browser_select_option, mcp__playwright__browser_press_key, mcp__playwright__browser_find, mcp__playwright__browser_snapshot, mcp__playwright__browser_wait_for, mcp__playwright__browser_console_messages, mcp__playwright__browser_take_screenshot
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
- `.claude/skills/price-watch/SKILL.md` — authoritative definition of the JSON shape and re-check logic; defer to it for any detail not covered here.
- `.agents/skills/{flights-search,stays-search,packages-search}/search.py` — used to re-search the same route/dates on re-check for adapter-backed trips.
- `.claude/skills/trivago-search/SKILL.md` — authoritative driver contract (server config, tool-capability mapping, etiquette limits) for re-checking browser-driven trips (`trivago-search`, `momondo-search`, `booking-search`); re-check dispatches to it rather than restating it here.

## State touched
- Reads/writes: `watchlist/<slug>.json` (one per trip; created, updated, or deleted).
- Never touches `profile/` or `trip_scraper/`.

## Before anything else
If this run needs profile data (e.g. resolving `<trip>` against profile-derived context, or any currency/preference defaults), check `profile/` first. If `profile/` doesn't exist or any file still contains `<!-- FILL IN -->` markers, stop and tell the user to run `/setup` first — do not proceed with a partial profile.

`profile/tooling.md` (driver preference) is exempt from that check: if it's absent, or present but missing the relevant field, do not stop or prompt `/setup` — the caller default (Playwright MCP) applies silently. An existing `profile/` predating this file must keep working with no migration.

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
2. For each watched trip, dispatch on `trip.source` (see `.claude/skills/price-watch/SKILL.md` "Re-check procedure" for the authoritative version of this logic):
   - **Adapter-backed** (`flights-search`, `stays-search`, `packages-search`): re-run the matching `.agents/skills/*/search.py --json` adapter for that same route/dates (falling back to web search when the adapter reports the no-credentials protocol — exit code 2, `status == "no_credentials"`, per `.claude/skills/trip-scraper/SKILL.md` — same as `/scrape`).
   - **Browser-driven** (`trivago-search`, `momondo-search`, `booking-search`): re-run the same search via the Playwright MCP driver per `.claude/skills/trivago-search/SKILL.md`'s driver contract. The terminal-outcome logic for this branch (fall through to web search on a chain-ending condition, then `available: false` with the reason in report text only, reported distinctly from a genuine sold-out) is authoritatively defined in `.claude/skills/price-watch/SKILL.md`'s "Re-check procedure" — followed here, not restated.
   - **Pasted** (`source: "pasted"`): no live re-query is possible — ask the user to re-paste, or skip with a note.
   Every trip must land in one of these three branches; none may fall through unhandled.
   - Compare the new price against the most recent entry in the trip's price history.
   - Classify the result: price drop, price rise, unchanged, sold-out/unavailable, or blocked read.
   - Append the new observation (timestamp, price, currency, availability) to the trip's price history array in `watchlist/<slug>.json`. The entry shape and `schema_version: 1` are unchanged, and entries never record which driver produced them.
3. Report a summary table across all watched trips: destination, dates, previous price, current price, delta, and status (drop / rise / unchanged / sold out / blocked read).
4. Highlight drops and sold-out warnings first — these are the actionable items. Report blocked reads separately from sold-out warnings; do not let a run with several blocked browser-driven trips read as mass sold-out.

## Scheduling
`/watch` (no args) is idempotent. Adapter-backed and browser-driven trips can both now be re-checked without a user present, since Playwright MCP — the default browser driver for `/watch` — runs headless and needs no attended session or extension permission (unlike `claude-in-chrome`, which cannot execute on a schedule at all). Unattended runs require the headless server config from the repo's tracked `.mcp.json`. Neither this unattended path nor the manual, attended Playwright path has yet been exercised against the real sites, so treat cron/CI scheduling as a known limitation rather than proven — verify the first few scheduled runs manually before relying on them. See `.claude/skills/price-watch/SKILL.md` for the re-check dispatch logic.

## Output
Updated `watchlist/<slug>.json` file(s) with appended price history, and a human-readable price-change report on each `/watch` (no-args) run.
