---
description: Search flights, stays, and packages against your profile and present fit-scored matches
argument-hint: "[optional steering, e.g. 'warm in late October, under €900/person, max 5h flight']"
allowed-tools: Read, Write, Bash, Glob, WebSearch, WebFetch
---

# /scrape — Search orchestration

## Purpose
Search configured sources for trips matching the traveler profile and the current date window,
deduplicate against previously seen results, score every candidate for fit, and present matches
sorted by fit score so the user can pick one for `/plan` or `/watch add`.

## Inputs
- `profile/01-traveler-profile.md` … `profile/06-packing-and-prep.md` — must exist and be filled.
- `$ARGUMENTS` — optional freeform steering (e.g. `warm in late October, under €900/person, max 5h flight`). Applies to this run only; never edits the profile.
- `.claude/skills/trip-scraper/search-queries.md` — default destinations, date windows, and sources.
- `.claude/skills/holiday-planner/03-trip-evaluation.md` — scoring framework.
- `.agents/skills/{flights-search,stays-search,packages-search}/search.py` — search adapters.
- `trip_scraper/seen.json` — previously seen candidates, for deduplication.

## State touched
- Reads: everything under Inputs above.
- Writes: `trip_scraper/seen.json` (append newly seen candidates), and a results snapshot under `trip_scraper/` (e.g. `trip_scraper/results-<date>.json`) for this run's output.
- Never edits `profile/` files.

## Steps

1. **Load the profile.** Read all six `profile/*.md` files. If `profile/` doesn't exist or any file still contains `<!-- FILL IN -->` markers, stop and tell the user to run `/setup` first — do not proceed with a partial profile.

2. **Merge steering args.** If `$ARGUMENTS` is present, parse it for overrides (season/dates, budget ceiling, max travel time, destination hints, etc.). These override the corresponding profile defaults **for this run only** — state clearly which defaults were overridden and with what value. Never write the override back into `profile/`.

3. **Read search defaults.** Read `.claude/skills/trip-scraper/search-queries.md` for the default destination list, date windows, and which sources to query. Combine with the merged profile + steering constraints (home airports, budget, dates, max travel time, style, dealbreakers) to build the concrete query parameters for this run.

4. **Invoke search adapters.** For each of `.agents/skills/flights-search/search.py`, `.agents/skills/stays-search/search.py`, `.agents/skills/packages-search/search.py`:
   - Run it with `--json` and the query parameters from step 3, via `python <path>/search.py --json <args>`.
   - If the CLI exits non-zero reporting missing credentials (e.g. no `AMADEUS_API_KEY`), fall back to Claude's own web search for that source instead of failing the whole run — note in the final output which sources used the API vs. web-search fallback.
   - Collect all raw candidates from all three sources.

5. **Deduplicate.** Read `trip_scraper/seen.json` (if absent, treat it as `{"schema_version": 1, "entries": {}}` — when writing it for the first time, include `schema_version`). Derive each candidate's dedupe key exactly as specified in `.claude/skills/trip-scraper/SKILL.md` — that file is the authority on the key derivation and the file format; do not invent an ad hoc match. For each candidate:
   - If its key is **not** present in `entries`, it's genuinely new — keep it for scoring and presentation.
   - If its key **is** present but the price has moved into a new price bucket, it's a legitimate price-change re-surface — keep it for scoring and presentation too (do not silently drop it).
   - If its key is present and the price bucket hasn't changed, it's a true repeat — drop it from this run's presented results, but still update its `last_seen` timestamp in `seen.json` (preserving the existing `first_seen`).

6. **Score each candidate.** Apply the scoring framework in `.claude/skills/holiday-planner/03-trip-evaluation.md` against the (merged) profile for every new candidate. Produce a fit score and the concrete reasoning behind it (which criteria it satisfies, which it violates, e.g. "fits budget and pace but exceeds max travel time by 40 minutes").

7. **Present results.** Sort by fit score, descending. For each candidate show: destination, dates, price per person (state currency, EUR default), source, fit score, and the reasoning from step 6. Rank a cheaper trip that violates a dealbreaker below a pricier one that fits — never let price alone determine order.

8. **Offer next actions.** After presenting the list, ask the user whether to:
   - Run `/plan <pick>` on one of the results, or
   - `/watch add <pick>` to save it to the price-tracking watchlist.

9. **Persist state.** Write the full set of new candidates (scored) to a `trip_scraper/` results snapshot. Update `trip_scraper/seen.json` per `.claude/skills/trip-scraper/SKILL.md`'s format: for each candidate seen this run (new, price-changed, or repeat), set/update its `last_seen` to this run's timestamp — set `first_seen` only when the entry didn't exist before, and never overwrite an existing `first_seen`. Add new entries and update existing ones; keep `schema_version` set.

## Output
A fit-sorted list of new trip candidates with price/person and scoring reasoning, plus updated `trip_scraper/` state.
