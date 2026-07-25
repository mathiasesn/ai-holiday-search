# Setup ai-holiday-search repo

## Problem / Why
The repo currently contains only `README.md`, `LICENSE`, and an empty `.claude/settings.local.json`.
The README fully describes a framework that does not exist yet. Nothing in the documented
workflow (`/setup`, `/scrape`, `/plan`, `/watch`, `/reset`) is runnable.

## Goals
- Materialize every path in the README's "File structure" tree.
- Implement the five slash commands as `.claude/commands/*.md`.
- Implement the core `holiday-planner` skill with its six numbered reference files.
- Implement `trip-scraper` and `price-watch` skills.
- Implement `.agents/skills/{flights-search,stays-search,packages-search}` as adapters, each
  with a `SKILL.md` **and an executable Python CLI** (ai-job-search portal-skill parity).
- Ship `tools/` (`lint_skills.py`, `security_guards.py`) and a `.github/workflows/ci.yml`
  running lint + guards + a smoke test of each search CLI's `--help`.
- Ship `CLAUDE.md` (workflow rules + pointer to the local profile), `SETUP.md`,
  `trip_tracker.csv.example`, and the `documents/` scaffold.
- Structurally resemble `MadsLorentzen/ai-job-search` (command/skill layout, drafter–reviewer
  pipeline, `.agents/skills` adapters, tracker CSV, SETUP.md).

## Non-goals
- Filling in any real travel profile — the repo ships as a fork-and-fill template usable
  by anyone; personal data stays local and untracked.
- PDF/LaTeX output. Itineraries are Markdown only; PDF moves to the Roadmap and the
  README's Prerequisites/`/plan` wording is updated accordingly.
- Notion/Gmail sync, or the Roadmap items (`/pack`, .ics export, multi-destination).
- Scraping sites that actively block bots — CLIs use public APIs/feeds and web search; the
  paste-a-listing fallback covers the rest.

## Constraints
- Claude Code CLI conventions: commands are Markdown with frontmatter; skills are
  `SKILL.md` + reference files.
- Python 3.10+ for any scripts; stdlib-only where possible.
- Everything degrades gracefully to Claude web search + paste-a-listing.
- `README.md` is the source of truth; the implementation adapts to it, not vice versa.
- MIT license, existing initial commit on `main`.
- **Locale**: all tracked files, prompts, and generated output in English so the repo is
  internationally usable. Example values are Danish/European: EUR (with DKK noted),
  CPH/BLL as example home airports, European example destinations — examples only, every
  one overridden by the local profile at `/setup`.

## Proposed approach
0. **Public template, local profile.** Everything tracked in git is generic and reusable.
   Personal data (filled-in profile, documents, itineraries, watchlist, scraper state) is
   gitignored. Tracked scaffolds are `*.example.md`; `/setup` copies them into the
   untracked working location and fills them in.
1. Scaffold directory tree + `.gitignore` (ignore generated/personal state: `profile/`,
   `itineraries/`, `watchlist/`, `trip_scraper/`, `trip_tracker.csv`,
   `documents/**` except its README).
2. Write `CLAUDE.md` with framework/workflow rules only (fit scoring, pacing enforcement,
   uncertainty flagging) plus a pointer to the local profile files; it must contain no
   personal data and must behave sanely before `/setup` has run.
3. Write the five commands, each self-contained with explicit step-by-step instructions.
4. Write `holiday-planner/SKILL.md` + `01`–`06` reference files with template content and
   `<!-- FILL IN -->` markers.
5. Write `trip-scraper` and `price-watch` skills defining state file formats
   (`trip_scraper/seen.json`, `watchlist/<slug>.json` price history).
6. Write the three `.agents/skills` adapters, each `SKILL.md` + `search.py`:
   - `flights-search/search.py` — Amadeus Self-Service API when `AMADEUS_API_KEY`/secret is
     set; exits with a clear "no credentials, use web search" status otherwise.
   - `stays-search/search.py` — public-API/feed based, web-search fallback documented.
   - `packages-search/search.py` — working template with a documented `parse_results()`
     seam for forking to a local charter operator.
   All CLIs: stdlib + `requests`, `--json` output, `--help`, non-zero exit on failure,
   never print secrets.
7. Write `tools/lint_skills.py` (every SKILL.md/command has required frontmatter and
   referenced files exist), `tools/security_guards.py` (no secrets tracked, .gitignore
   covers personal paths), and `.github/workflows/ci.yml`.
8. Write `SETUP.md`, `trip_tracker.csv.example` header row, `documents/README.md`,
   `requirements.txt`.
9. Verify: `python tools/lint_skills.py` and `security_guards.py` pass, each `search.py
   --help` runs, tree matches README.

## Acceptance criteria
- Every file/folder in the README tree exists and is non-empty (state dirs contain
  `.gitkeep` or a README).
- `/setup`, `/scrape`, `/plan`, `/watch`, `/reset` appear in Claude Code's command list.
- Each command file describes its full workflow, inputs, outputs, and state files.
- `/plan`'s command file encodes all 7 numbered steps from the README, including spawning
  a reviewer subagent and the verification checklist.
- `/reset` supports `profile`, `watchlist`, `all` and requires typing `RESET`.
- `search-queries.md` (referenced in Customization table) exists at a documented location.
- No secrets committed; `.gitignore` covers generated state and personal documents.
- `git status` is clean after running `/setup` and `/plan` — no personal data staged.
- A fresh clone by any user works with zero edits to tracked files.
- `python tools/lint_skills.py` and `python tools/security_guards.py` exit 0; each
  `.agents/skills/*/search.py --help` exits 0 with no credentials set.
- README updated so PDF appears only under Roadmap, not Prerequisites or `/plan` step 7.

## Open questions
_None._

## Risks
- README describes behavior that only works if commands are written very explicitly;
  vague command files will produce inconsistent runs.
- Booking sites block automated access — search quality depends heavily on the
  paste-a-listing fallback being well specified.
- Scope is large (~30 files); risk of thin, boilerplate content that looks complete but
  doesn't actually steer the model.
