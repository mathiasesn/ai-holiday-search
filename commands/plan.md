---
description: Drafter-reviewer workflow that turns a destination or pasted listing into a verified, budgeted day-by-day Markdown itinerary
argument-hint: "<destination and dates> | <paste a listing, package, or booking-page text>"
allowed-tools: Read, Write, Glob, Task, Agent, WebSearch, WebFetch
---

# /plan — Drafter-reviewer itinerary workflow

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
Turn a destination request or a pasted listing/package/booking-page text into a fully verified,
day-by-day Markdown itinerary with a budget table, produced by a drafter agent and independently
critiqued by a fresh-context reviewer agent before being presented to the user.

## Inputs
- `$ARGUMENTS` — either `<destination>, <nights>, <timing>` (e.g. "Lisbon, 5 nights in March") or pasted freeform listing/package/booking-page text.
- `<DATA_ROOT>/profile/01-traveler-profile.md` … `<DATA_ROOT>/profile/06-packing-and-prep.md` — must exist and be filled (run `/setup` first if not).
- `<FRAMEWORK_ROOT>/skills/holiday-planner/03-trip-evaluation.md` — fit scoring.
- `<FRAMEWORK_ROOT>/skills/holiday-planner/04-itinerary-templates.md` — day-plan structure and pacing rules.
- `<FRAMEWORK_ROOT>/skills/holiday-planner/05-budget-rules.md` — budget categories, verification, buffers.

## Output
- `<DATA_ROOT>/itineraries/<trip-slug>/itinerary.md` — final Markdown itinerary (Markdown only — never PDF), including the verification checklist and a booking to-do list.

## State touched
- Reads: all `<DATA_ROOT>/profile/*.md`, the holiday-planner skill reference files above.
- Writes: `<DATA_ROOT>/itineraries/<trip-slug>/itinerary.md` (and any supporting notes in that same folder, e.g. a budget worksheet, if useful).
- Does not modify `<DATA_ROOT>/profile/`, `<DATA_ROOT>/trip_scraper/`, or `<DATA_ROOT>/watchlist/`.

This command executes the following seven steps **explicitly and in order**. Do not skip, reorder, or merge steps.

## Step 1 — Parse
Determine which form `$ARGUMENTS` takes:
- A destination request (`<place>, <nights> nights, <timing>`), or
- Pasted listing/package/booking-page text.

If it's pasted text, extract destination, dates or date window, nights, price if stated, and any included inclusions (flights, transfers, board basis). If neither a clear destination nor usable pasted content is present, ask the user to clarify before continuing.

## Step 2 — Evaluate fit
Load the full profile (`<DATA_ROOT>/profile/01-traveler-profile.md` … `06-packing-and-prep.md`). If `<DATA_ROOT>/profile/` doesn't exist or any file still contains `<!-- FILL IN -->` markers, stop and tell the user to run `/setup` first — do not proceed with a partial profile.

Score the parsed destination/listing against the profile using `<FRAMEWORK_ROOT>/skills/holiday-planner/03-trip-evaluation.md` — style, budget, travel time, season, group needs, dealbreakers.

**If it's a poor match, say so honestly and up front**, before drafting anything: name the specific violated criteria (e.g. "exceeds your stated max travel time by 3h", "no direct flights and you flagged that as a dealbreaker"). Ask the user whether to proceed anyway, adjust the request, or stop. Only continue to Step 3 once the user confirms they want to proceed (or the fit is clearly good).

## Step 3 — Draft
Produce a day-by-day itinerary draft:
- One entry per day following the structure and pacing limits in `<FRAMEWORK_ROOT>/skills/holiday-planner/04-itinerary-templates.md` (e.g. max anchor activities/day, rest-day cadence) as defined in the user's profile. These pacing limits are hard constraints on the draft, not suggestions — do not draft a day that exceeds them.
- A budget table per `<FRAMEWORK_ROOT>/skills/holiday-planner/05-budget-rules.md` with rows for: transport, stay, activities, food estimate, buffer. Use the profile's currency (EUR default, DKK noted if relevant). Mark every estimated figure as a web-search estimate, not a confirmed price.
- Keep this as a working draft in memory/scratch — do not present it to the user yet.

## Step 4 — Spawn a reviewer agent with fresh context
Spawn a subagent via the subagent tool (`Task`, called `Agent` in some Claude Code builds) to review the draft independently. The reviewer **must not see this planning conversation** — it receives only the draft itinerary text and the destination/dates, nothing else. Use this exact brief (fill in the bracketed values from the draft):

```
You are an independent itinerary reviewer. You have NOT seen any planning conversation —
you are reviewing this draft cold, on its own merits. Do not assume anything about the
travelers beyond what's in the draft itself.

DRAFT ITINERARY:
[insert the full Step 3 draft: day-by-day plan + budget table]

DESTINATION: [destination]
DATES: [date window]

Your job is to independently research and attack this draft:
1. Research weather norms for [destination] during [dates]. Flag any activity that is a
   poor fit for likely conditions (e.g. outdoor-heavy plans in rainy/off-season weather).
2. Check opening days/hours for every named venue or activity in the draft. Flag anything
   that is likely closed on the day it's scheduled, or check seasonal closures.
3. Check for local events, festivals, holidays, or closures during that week that would
   affect crowding, prices, or availability.
4. Check for common scams and tourist traps at this destination and flag any itinerary
   item that walks into one, or any neighborhood/venue with a known bad reputation.
5. Sanity-check travel legs between consecutive activities each day for feasibility
   (distance/time, not just straight-line assumption).

Be specific and critical. For each issue found, name the exact day/item, explain the
problem, and suggest a concrete fix or alternative. Do not soften findings to be polite —
the drafter will revise based on your critique. If you cannot verify something via search,
say so explicitly rather than guessing.

Return your findings as a structured list of issues (day/item, problem, suggested fix).
```

Run this as a single subagent call (foreground — the plan cannot proceed without its findings) and wait for its structured findings before continuing.

## Step 5 — Revise
Using the reviewer's findings, revise the draft: swap out closed/poor-fit venues, adjust days flagged for weather or events, fix infeasible travel legs, add scam/tourist-trap warnings where relevant, and update the budget table if changes affect cost. Address every issue the reviewer raised — either fix it or explicitly note why it's being kept as-is with justification.

## Step 6 — Verify
Before presenting anything, run this verification checklist against the revised itinerary. If any check fails, loop back to Step 5 (revise again) — do not present a plan that fails verification:
- [ ] Every budget table's rows sum correctly to the stated total (transport + stay + activities + food + buffer).
- [ ] No day exceeds the pacing rules defined in the user's profile (`04-itinerary-templates.md` limits, e.g. max anchor activities/day, required rest-day cadence). Pacing limits are enforced, not suggested: if any day breaks them, that is a hard reject — force a revision (loop back to Step 5) rather than noting it for the user to weigh.
- [ ] Every named venue/activity has been confirmed to exist via search (not just assumed).
- [ ] Travel legs between consecutive activities on each day are feasible given transit/drive times.

## Step 7 — Present
Write the final itinerary to `<DATA_ROOT>/itineraries/<trip-slug>/itinerary.md` (derive `<trip-slug>` from destination + date window, e.g. `lisbon-2026-03`) as Markdown — never PDF, never mention PDF as an option. Report the absolute path since `<DATA_ROOT>` may lie outside the current project. The file must include, in this order:
1. Trip summary (destination, dates, nights, fit-score summary from Step 2).
2. Day-by-day itinerary.
3. Budget table with total.
4. The Step 6 verification checklist, shown as completed (checked) items.
5. A booking to-do list (what still needs to be booked/confirmed, in order).
6. Any uncertainty flags carried over from drafting/review (e.g. "price is a web-search estimate, verify at booking").

Print the same content to the chat for the user, and confirm the file path it was saved to.
