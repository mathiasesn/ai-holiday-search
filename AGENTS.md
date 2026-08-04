# AI Holiday Search — Framework Rules

This file defines how Claude Code should behave in this repository. It contains **no
personal travel data** — your actual traveler profile lives in the gitignored `profile/`
folder, written by `/setup`. This file is tracked in git and shared by everyone who forks
this template.

Read `ARCHI.md` before making changes — it is the architecture source of truth (structure,
stack, conventions). This file remains the authority on behavior.

## Before `/setup` has been run

If `profile/` does not exist yet, treat this as a fresh checkout:

- Do not invent a traveler profile or assume preferences.
- For any command that needs profile data (`/scrape`, `/plan`, `/watch`), tell the user to
  run `/setup` first, then stop.
- You may still explain what each command does, read `README.md`/`SETUP.md`, or answer
  general questions about the framework.
- As a fallback for *reading* what fields a profile needs, consult the `<!-- FILL IN -->`
  templates in `.claude/skills/holiday-planner/01-traveler-profile.md` through
  `06-packing-and-prep.md` — but never treat their example content as a real user's data.

## The five commands

| Command | When to use it |
| --- | --- |
| `/setup` | First run, or whenever the traveler profile needs updating. Reads `documents/`, a pasted freeform description, or runs an interview — whichever the user has available. Safe to re-run. |
| `/scrape` | To search for trips matching (or overriding) the current profile. Produces a fit-scored shortlist, not a raw dump of listings. |
| `/plan <destination or pasted listing>` | To turn a specific destination or listing into a reviewed, budgeted day-by-day itinerary. |
| `/watch` | To re-check saved trips for price changes. `/watch add <trip>` saves one; `/watch remove <trip>` drops one. |
| `/reset` | To wipe profile and/or watchlist data locally. Requires typing `RESET` to confirm. Never run without explicit user intent. |

## Fit scoring

`/scrape` and the evaluate-fit step of `/plan` must score every trip against the traveler
profile and **show the reasoning**, not just a number. A cheap trip that violates a stated
dealbreaker (e.g. "no direct flight" when direct-only is a dealbreaker) ranks **below** a
pricier trip that fits — never let raw price override a violated dealbreaker in the
ordering. Say plainly when a trip is a poor match rather than dressing it up.

## Pacing rules are enforced, not suggested

The traveler profile defines pacing limits (e.g. max anchor activities per day, minimum
"nothing planned" days per week). These are hard constraints on `/plan`'s drafting and
verification steps:

- The drafter must respect them when building the day-by-day itinerary.
- The verification step in `/plan` must actively check the draft against them and
  **reject and force a revision** if any day breaks the limits — this is not a soft
  suggestion left for the user to notice.

## Explicit uncertainty flagging

Never present a guess as a fact. Anything not confirmed by a live search or an
authoritative source must be labeled as an estimate, e.g. "price is a web-search estimate,
verify at booking" or "opening hours unconfirmed for these dates." This applies to prices,
opening hours, weather expectations, and venue existence.

## Paste-anything fallback

Many booking sites block automated access. Any pasted listing, package description, or
confirmation-email text is a valid input to `/plan` (and to `/scrape` steering) and must
enter the same evaluate → draft → review → verify pipeline as a searched result — it does
not get a lesser or ad hoc treatment.

## Local vs. tracked data — read this before touching profile data

- **`profile/`** (gitignored) is the authoritative traveler profile once `/setup` has been
  run. Always prefer it over anything else when it exists.
- **`.claude/skills/holiday-planner/01-*.md` through `06-*.md`** (tracked) contain generic
  templates with `<!-- FILL IN -->` markers. They document the *shape* of the profile
  fields for anyone reading the repo — they are not a substitute for a real profile. If
  `profile/` is absent, tell the user to run `/setup`; do not silently plan against the
  template placeholders.
- **`documents/`** (gitignored except `README.md` and the `.gitkeep` placeholders) holds
  raw source material `/setup` reads from — not itself a profile format.
- **`itineraries/`, `watchlist/`, `trip_scraper/`, `trip_tracker.csv`** (all gitignored)
  are generated/working state, never framework content.

## Hard rule: never commit personal data

Never stage or commit anything under `profile/`, `documents/past-trips/`,
`documents/preferences/`, `itineraries/`, `watchlist/`, `trip_scraper/`,
`trip_tracker.csv`, `.env`, or any API key/secret. If asked to commit changes, check
`git status` first and flag anything that looks like personal data or a secret before
proceeding — do not `git add -A` blindly in this repo.
