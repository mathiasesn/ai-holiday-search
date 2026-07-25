# AI Holiday Search

An AI-powered holiday planning framework built on [Claude Code](https://claude.com/claude-code). Fork it, fill in your travel profile, and let Claude find trips that fit you, score them against your preferences, build reviewed day-by-day itineraries, and watch prices until you book.

*Inspired by the structure of [ai-job-search](https://github.com/MadsLorentzen/ai-job-search).*

## What this is

A structured workflow that turns Claude Code into a full-stack holiday planning assistant. The core workflow (traveler profiling, fit evaluation, and the drafter–reviewer itinerary pipeline) is **destination- and country-agnostic**. Search skills are built around public APIs and web search, with a paste-a-listing fallback for any site that blocks automated access — the pattern is designed so you can add skills for your local charter operators or favorite booking sites.

```
/setup            /scrape               /plan <destination>        /watch
  |                  |                        |                       |
  v                  v                        v                       v
Fill in          Search flights,         Evaluate fit            Track saved
your travel      stays, packages         Score & recommend       trips
profile              |                        |                       |
  v                  v                        v                       v
Profile          Present matches         Draft itinerary +       Alert on
files ready      with fit ratings        budget (day-by-day)     price drops
                     |                        |
                     v                        v
                 Pick a match            Reviewer agent critiques
                 -> /plan                -> Revise -> Final itinerary
```

The framework encodes trip-planning best practices: structured fit criteria, realistic pacing (no 6-museums-a-day itineraries), budget verification, and a second-agent review that checks the plan against reality — opening hours, seasonal weather, local events, and known tourist traps.

## Prerequisites

- [Claude Code](https://claude.com/claude-code) (CLI)
- Python 3.10+
- (Optional) API keys for flight/accommodation search — see [Search sources](#search-sources). Everything degrades gracefully to Claude's web search + paste-a-listing mode.

## Quick start

### 1. Fork and clone

```
gh repo fork <you>/ai-holiday-search --clone
cd ai-holiday-search
```

### 2. Set up your profile

```
claude
# Then inside Claude Code:
/setup
```

`/setup` offers three paths: read your `documents/` folder if populated (past itineraries, booking confirmations, a "trips we loved / trips we hated" note), import a freeform description pasted in chat, or walk through an interview. It auto-detects what you have and asks. Documents-folder mode is idempotent and safe to re-run as you add more material.

The interview covers:

- **Who's traveling** — adults, kids and ages, pets, mobility constraints
- **Constraints** — home airport(s), budget range, dates and how flexible they are, max travel time, visa/passport situation
- **Style** — beach vs. city vs. nature vs. ski, pace (packed vs. relaxed), accommodation standard, food priorities
- **Dealbreakers and must-haves** — pool, walkability, direct flights only, no hostels, etc.
- **History** — where you've been, what worked, what didn't (this is the highest-value input)

### 3. Search for trips

```
/scrape
```

Searches configured sources for trips matching your profile and current date window, deduplicates, and presents them **sorted by fit score** with price per person and the reasoning behind each score. Pick a match to run `/plan` on it directly.

You can also steer a single run without editing your profile:

```
/scrape warm in late October, under €900/person, max 5h flight
```

### 4. Plan a trip

```
/plan Lisbon, 5 nights in March
```

If you found a specific package or listing elsewhere, paste it instead:

```
/plan <paste the listing, package description, or booking page text here>
```

This runs the full workflow: evaluate fit, draft a day-by-day itinerary with budget, review with a second agent, revise, and present the final output with a verification checklist.

### 5. Watch prices

```
/watch add <trip>     # save a trip from /scrape or /plan to the watchlist
/watch                # re-check all watched trips, report price changes
/watch remove <trip>
```

`/watch` stores a snapshot of each saved trip in `watchlist/` and, on each run, re-searches the same route/dates and reports drops, rises, and sold-out warnings. Run it manually or schedule it (cron, CI, or Claude Code on a recurring task).

## File structure

```
ai-holiday-search/
├── CLAUDE.md                            # Framework/workflow rules only (no personal data)
├── .claude/
│   ├── commands/
│   │   ├── setup.md                     # /setup onboarding (documents, paste, or interview)
│   │   ├── scrape.md                    # /scrape search orchestration
│   │   ├── plan.md                      # /plan drafter–reviewer itinerary workflow
│   │   ├── watch.md                     # /watch price tracking
│   │   └── reset.md                     # /reset wipe profile data
│   ├── skills/
│   │   ├── holiday-planner/             # Core planning skill
│   │   │   ├── SKILL.md                 # Skill definition
│   │   │   ├── 01-traveler-profile.md   # Who travels, constraints, budget
│   │   │   ├── 02-travel-style.md       # Pace, taste, accommodation standard
│   │   │   ├── 03-trip-evaluation.md    # Scoring framework for trip fit
│   │   │   ├── 04-itinerary-templates.md# Day-plan structure + pacing rules
│   │   │   ├── 05-budget-rules.md       # Cost categories, verification, buffers
│   │   │   └── 06-packing-and-prep.md   # Packing lists, docs, insurance checklist
│   │   ├── trip-scraper/                # Search orchestration across sources
│   │   └── price-watch/                 # Snapshot + re-check logic
│   └── settings.local.json              # Claude Code permissions
├── .agents/skills/                      # Search source skills (add your own)
│   ├── flights-search/                  # Flight search (API or web-search based)
│   ├── stays-search/                    # Hotels / rentals
│   └── packages-search/                 # Package holidays / charters (template)
├── documents/                           # Source material for /setup
│   ├── README.md                        # Folder layout instructions
│   ├── past-trips/                      # Old itineraries, booking confirmations
│   └── preferences/                     # Freeform notes on likes/dislikes
├── itineraries/                         # /plan output (one folder per trip)
├── watchlist/                           # /watch state (trip snapshots, price history)
├── trip_scraper/                        # Scraper state (seen trips, results)
├── trip_tracker.csv.example             # Shortlist tracking spreadsheet template (copy to trip_tracker.csv, gitignored)
├── tools/
│   ├── lint_skills.py                   # Validates SKILL.md/command frontmatter and cross-links
│   └── security_guards.py               # Guards against committed secrets and personal-data leaks
├── .github/workflows/ci.yml             # CI: runs the lint and security guards on every push
├── requirements.txt                     # Python dependencies (requests)
└── SETUP.md                             # Detailed setup guide
```

## How `/plan` works

The `/plan` command runs a **drafter–reviewer workflow** with mandatory verification:

1. **Parse** the destination request or pasted listing
2. **Evaluate fit** against your profile (style, budget, travel time, season, group needs) and say honestly if it's a poor match before spending effort on it
3. **Draft** a day-by-day itinerary with a budget table: transport, stay, activities, food estimate, buffer
4. **Spawn a reviewer agent** with fresh context that researches the destination — weather norms for your dates, opening days/hours of proposed activities, local events or closures that week, common scams and tourist traps — and critiques the draft
5. **Revise** based on the reviewer's feedback
6. **Verify** the final plan: budget rows sum correctly, no day exceeds the pacing rules in your profile, every named venue was confirmed to exist via search, travel legs between activities are feasible
7. **Present** the final itinerary (Markdown) with the verification checklist and a booking to-do list

All recommendations are grounded in your actual profile. The system flags uncertainty explicitly (e.g., "price is a web-search estimate, verify at booking") rather than presenting guesses as facts.

### What makes this workflow different

- **Fit scoring, not browsing.** `/scrape` doesn't dump listings; it scores each trip against your stated constraints and history and shows the reasoning. A cheap trip that violates a dealbreaker ranks below a pricier one that fits.
- **Reviewer with fresh eyes.** The drafter plans; a second agent that hasn't seen your conversation researches the destination independently and attacks the draft: "the palace is closed Tuesdays," "that's rainy season," "this neighborhood is a 40-minute transfer from everything else." The drafter then revises.
- **Pacing rules are enforced, not suggested.** Your profile defines limits (e.g., max 2 anchor activities/day with kids, one "nothing planned" day per 5 nights) and the verification step rejects itineraries that break them.
- **Paste-anything fallback.** Booking sites aggressively block bots. Any listing, package page, or confirmation email can be pasted as text and enters the same evaluate → plan → review pipeline.

## Search sources

The skills in `.agents/skills/` are intentionally thin adapters. Out of the box:

| Source          | Method                                  | Setup                    |
| --------------- | --------------------------------------- | ------------------------ |
| Flights         | Amadeus Self-Service API (free tier) or web search | `AMADEUS_API_KEY` (optional) |
| Stays           | Web search + paste-a-listing            | none                     |
| Packages        | Template skill — add your local operators | fork and edit          |

Adding a source = copying a skill folder, pointing it at a site or API, and describing the result format in its SKILL.md. PRs adding country-specific package/charter skills are welcome — that's the intended way this grows.

## Customization

| File                        | What to change                                              |
| --------------------------- | ----------------------------------------------------------- |
| `profile/` (gitignored, written by `/setup`) | Your full travel profile — group composition, budget, home airports, constraints, style, history |
| `01-traveler-profile.md`    | Group composition, budget, home airports, constraints       |
| `02-travel-style.md`        | Pace, taste, standards, dealbreakers                        |
| `03-trip-evaluation.md`     | Fit-scoring weights (e.g., budget vs. flight time)          |
| `04-itinerary-templates.md` | Day structure, pacing limits, output format                 |
| `search-queries.md`         | Default destinations, date windows, and sources for /scrape |

### Starting over

```
/reset profile    # clears profile files, preserves framework rules
/reset watchlist  # clears saved trips and price history
/reset all        # both
```

`/reset` shows exactly what will be deleted and requires you to type `RESET` to confirm.

## Tips for better results

**Profile depth matters.** The single biggest quality factor is trip history with opinions attached. "Loved Ljubljana because it was walkable and low-key; hated the Mallorca resort because we were trapped without a car" gives the fit scorer far more to work with than a list of countries visited.

**Be honest about pace.** Most itinerary tools overpack. State your real limits during `/setup` — the verification step will enforce them.

**Use flexibility.** "Somewhere warm, any week in October, from these two airports" gives `/scrape` room to find outliers that fixed-date searches never surface.

## Roadmap

- [ ] `/pack` — profile-aware packing list generation per trip
- [ ] Multi-destination trips (open-jaw flights, rail legs)
- [ ] Calendar export (.ics) of final itineraries
- [ ] Community skills for national charter operators
- [ ] PDF/LaTeX itinerary compilation (Markdown output is the default; PDF is optional future tooling)

## License

MIT
