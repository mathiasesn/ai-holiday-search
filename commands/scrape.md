---
description: Search flights, stays, and packages against your profile and present fit-scored matches
argument-hint: "[optional steering, e.g. 'warm in late October, under €900/person, max 5h flight']"
allowed-tools: Read, Write, Bash, Glob, WebSearch, WebFetch, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__find, mcp__claude-in-chrome__form_input, mcp__playwright__browser_tabs, mcp__playwright__browser_navigate, mcp__playwright__browser_fill_form, mcp__playwright__browser_type, mcp__playwright__browser_click, mcp__playwright__browser_select_option, mcp__playwright__browser_press_key, mcp__playwright__browser_find, mcp__playwright__browser_snapshot, mcp__playwright__browser_wait_for, mcp__playwright__browser_console_messages, mcp__playwright__browser_take_screenshot
---

# /scrape — Search orchestration

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
Search configured sources for trips matching the traveler profile and the current date window,
deduplicate against previously seen results, score every candidate for fit, and present matches
sorted by fit score so the user can pick one for `/plan` or `/watch add`.

## Inputs
- `<DATA_ROOT>/profile/01-traveler-profile.md` … `<DATA_ROOT>/profile/06-packing-and-prep.md` — must exist and be filled.
- `<DATA_ROOT>/profile/tooling.md` — optional. Holds the browser-driver preference for this run. If absent, or present but missing the driver field, default to `claude-in-chrome` (see step 0 for the absence rule).
- `$ARGUMENTS` — optional freeform steering (e.g. `warm in late October, under €900/person, max 5h flight`). Applies to this run only; never edits the profile.
- [../skills/trip-scraper/search-queries.md](../skills/trip-scraper/search-queries.md) — default destinations, date windows, and sources.
- [../skills/holiday-planner/03-trip-evaluation.md](../skills/holiday-planner/03-trip-evaluation.md) — scoring framework.
- `<FRAMEWORK_ROOT>/.agents/skills/{flights-search,stays-search,packages-search}/search.py` — search adapters.
- [../skills/trivago-search/SKILL.md](../skills/trivago-search/SKILL.md) — browser-driven trivago.dk stays source.
- [../skills/momondo-search/SKILL.md](../skills/momondo-search/SKILL.md) — browser-driven momondo.dk source covering flights, stays, and packages.
- [../skills/booking-search/SKILL.md](../skills/booking-search/SKILL.md) — browser-driven booking.com source covering stays and flights only (no packages).
- `<DATA_ROOT>/trip_scraper/seen.json` — previously seen candidates, for deduplication.

## State touched
- Reads: everything under Inputs above.
- Writes: `<DATA_ROOT>/trip_scraper/seen.json` (append newly seen candidates), and a results snapshot under `<DATA_ROOT>/trip_scraper/` (e.g. `<DATA_ROOT>/trip_scraper/results-<date>.json`) for this run's output.
- Never writes or edits `<DATA_ROOT>/profile/` files — only `/setup` does. (Reads `<DATA_ROOT>/profile/tooling.md` if present, but never writes it.)
- Opens a browser tab for the `trivago-search`, `momondo-search`, and `booking-search` steps, using
  whichever driver is resolved in step 0 below (`claude-in-chrome` by default, or Playwright MCP if
  `<DATA_ROOT>/profile/tooling.md` opts in) — but only on runs whose resolved query calls for that source's
  vertical (e.g. no `trivago-search` tab on a flights-only or packages-only run). `momondo-search`
  and `booking-search` each cover whichever of their verticals the run calls for; `booking-search`'s
  stays and flights verticals share one browser session and one permission check with each other.

## Steps

0. **Resolve the browser driver.** Read `<DATA_ROOT>/profile/tooling.md` if it exists. If the file or its `/scrape` driver field is absent, use the default `claude-in-chrome`; if present, honor whatever it specifies (`claude-in-chrome` or Playwright MCP). This absence is normal and silent — it is not a profile-completeness problem and must not trigger step 1's check.

1. **Load the profile.** Read the six numbered files. If `<DATA_ROOT>/profile/` doesn't exist or any of those six still contains `<!-- FILL IN -->` markers, stop and tell the user to run `/setup` first — do not proceed with a partial profile.

2. **Merge steering args.** If `$ARGUMENTS` is present, parse it for overrides (season/dates, budget ceiling, max travel time, destination hints, etc.). These override the corresponding profile defaults **for this run only** — state clearly which defaults were overridden and with what value. Never write the override back into `<DATA_ROOT>/profile/`.

3. **Read search defaults.** Read [../skills/trip-scraper/search-queries.md](../skills/trip-scraper/search-queries.md) for the default destination list, date windows, and which sources to query. Combine with the merged profile + steering constraints (home airports, budget, dates, max travel time, style, dealbreakers) to build the concrete query parameters for this run.

4. **Invoke search adapters.** For each of `<FRAMEWORK_ROOT>/.agents/skills/flights-search/search.py`, `<FRAMEWORK_ROOT>/.agents/skills/stays-search/search.py`, `<FRAMEWORK_ROOT>/.agents/skills/packages-search/search.py`:
   - Run it with `--json` and the query parameters from step 3, via `uv run --script "<FRAMEWORK_ROOT>/.agents/skills/<name>/search.py" --json <args>`.
   - If the CLI exits with code 2 and prints a JSON object with `status == "no_credentials"` (the adapter protocol defined in [../skills/trip-scraper/SKILL.md](../skills/trip-scraper/SKILL.md)), fall back to Claude's own web search for that source instead of failing the whole run — note in the final output which sources used the API vs. web-search fallback.
   - Collect all raw candidates from all three sources.

   If the resolved query for this run has a stay component (i.e. it isn't a flights-only or
   packages-only run), also run `trivago-search` as a second, first-class stays source,
   following [../skills/trivago-search/SKILL.md](../skills/trivago-search/SKILL.md). It has no CLI and no exit code, so it
   can't fail this way — instead it follows its own fallback chain, defined authoritatively in
   that skill's `SKILL.md` (do not re-enumerate the triggers here). The run must complete even
   when the resolved driver is unavailable. Note in the final output which sources used a live
   source (API or browser) vs. a fallback.

   Also run `momondo-search` as a first-class source across whichever of flights/stays/packages
   the resolved query calls for, following [../skills/momondo-search/SKILL.md](../skills/momondo-search/SKILL.md). Like
   `trivago-search`, it has no CLI and no exit code — it follows its own fallback chain, defined
   authoritatively in that skill's `SKILL.md` (do not re-enumerate the triggers here). Which of
   its verticals run is governed by the "Vertical selection" rule in
   [../skills/trip-scraper/SKILL.md](../skills/trip-scraper/SKILL.md). The run must complete even when the resolved driver is
   unavailable.

   Also run `booking-search` as a first-class source across whichever of stays/flights the
   resolved query calls for, following [../skills/booking-search/SKILL.md](../skills/booking-search/SKILL.md). Like
   `momondo-search`, it has no CLI and no exit code and follows its own fallback chain, defined
   authoritatively in that skill's `SKILL.md` (do not re-enumerate the triggers here). It has
   **no packages vertical** — booking.com has no bundled flight+hotel package product. Its stays
   and flights verticals share one browser session and one permission check with each other, and
   are selected by the same "Vertical selection" rule. The run must complete even when the
   resolved driver is unavailable.

5. **Deduplicate.** Read `<DATA_ROOT>/trip_scraper/seen.json` (if absent, treat it as `{"schema_version": 1, "entries": {}}` — when writing it for the first time, include `schema_version`). Derive each candidate's dedupe key exactly as specified in [../skills/trip-scraper/SKILL.md](../skills/trip-scraper/SKILL.md) — that file is the authority on the key derivation and the file format; do not invent an ad hoc match. For each candidate:
   - If its key is **not** present in `entries`, it's genuinely new — keep it for scoring and presentation.
   - If its key **is** present but the price has moved into a new price bucket, it's a legitimate price-change re-surface — keep it for scoring and presentation too (do not silently drop it).
   - If its key is present and the price bucket hasn't changed, it's a true repeat — drop it from this run's presented results, but still update its `last_seen` timestamp in `seen.json` (preserving the existing `first_seen`).

6. **Score each candidate.** Apply the scoring framework in [../skills/holiday-planner/03-trip-evaluation.md](../skills/holiday-planner/03-trip-evaluation.md) against the (merged) profile for every new candidate. Produce a fit score and the concrete reasoning behind it (which criteria it satisfies, which it violates, e.g. "fits budget and pace but exceeds max travel time by 40 minutes").

7. **Present results.** Sort by fit score, descending. For each candidate show: destination, dates, price per person (state currency, EUR default), source, fit score, and the reasoning from step 6. Rank a cheaper trip that violates a dealbreaker below a pricier one that fits — never let price alone determine order. Where the same property was surfaced by more than one enabled source, show both rows separately, each with its own price and source, visibly grouped as the same property, and score/rank it once using the lower of the two prices — per [../skills/trip-scraper/SKILL.md](../skills/trip-scraper/SKILL.md).

8. **Offer next actions.** After presenting the list, ask the user whether to:
   - Run `/plan <pick>` on one of the results, or
   - `/watch add <pick>` to save it to the price-tracking watchlist.

9. **Persist state.** Write the full set of new candidates (scored) to a `<DATA_ROOT>/trip_scraper/` results snapshot. Update `<DATA_ROOT>/trip_scraper/seen.json` per [../skills/trip-scraper/SKILL.md](../skills/trip-scraper/SKILL.md)'s format: for each candidate seen this run (new, price-changed, or repeat), set/update its `last_seen` to this run's timestamp — set `first_seen` only when the entry didn't exist before, and never overwrite an existing `first_seen`. Add new entries and update existing ones; keep `schema_version` set.

## Notes on uncertainty
Prices, availability, and opening hours are frequently not confirmed by a live authoritative
source (API responses that are cached/stale, web-search results, or a browser read that got
partial data). Any such figure must be labeled as an estimate to verify at booking — never
present a guess as a confirmed fact.

## Output
A fit-sorted list of new trip candidates with price/person and scoring reasoning, plus updated `<DATA_ROOT>/trip_scraper/` state.
