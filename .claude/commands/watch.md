---
description: Save trips to a price watchlist and re-check them for price drops, rises, or sold-out status
argument-hint: "add <trip> | remove <trip> | (no args: re-check all watched trips)"
allowed-tools: Read, Write, Bash, Glob, WebSearch, WebFetch
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
- `.agents/skills/{flights-search,stays-search,packages-search}/search.py` — used to re-search the same route/dates on re-check.

## State touched
- Reads/writes: `watchlist/<slug>.json` (one per trip; created, updated, or deleted).
- Never touches `profile/` or `trip_scraper/`.

## Before anything else
If this run needs profile data (e.g. resolving `<trip>` against profile-derived context, or any currency/preference defaults), check `profile/` first. If `profile/` doesn't exist or any file still contains `<!-- FILL IN -->` markers, stop and tell the user to run `/setup` first — do not proceed with a partial profile.

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
2. For each watched trip:
   - Read its stored search parameters (route, dates, source).
   - Re-run the relevant `.agents/skills/*/search.py --json` adapter(s) for that same route/dates (falling back to web search when the adapter reports the no-credentials protocol — exit code 2, `status == "no_credentials"`, per `.claude/skills/trip-scraper/SKILL.md` — same as `/scrape`).
   - Compare the new price against the most recent entry in the trip's price history.
   - Classify the result: price drop, price rise, unchanged, or sold-out/unavailable.
   - Append the new observation (timestamp, price, currency, availability) to the trip's price history array in `watchlist/<slug>.json`.
3. Report a summary table across all watched trips: destination, dates, previous price, current price, delta, and status (drop / rise / unchanged / sold out).
4. Highlight drops and sold-out warnings first — these are the actionable items.

## Scheduling
`/watch` (no args) is idempotent and safe to run unattended. It can be scheduled via cron or CI to run periodically (e.g. daily) and report changes without user interaction. See `.claude/skills/price-watch/SKILL.md` for any automation notes.

## Output
Updated `watchlist/<slug>.json` file(s) with appended price history, and a human-readable price-change report on each `/watch` (no-args) run.
