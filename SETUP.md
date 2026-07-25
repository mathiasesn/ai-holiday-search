# Setup guide

This guide covers getting a fresh fork of **ai-holiday-search** running end to end.

## Prerequisites

- [Claude Code](https://claude.com/claude-code) (CLI)
- [uv](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`,
  or via Homebrew/pipx/winget (see the
  [installation guide](https://docs.astral.sh/uv/getting-started/installation/)). uv
  provisions its own Python, so a system Python install is not required.
- (Optional) `AMADEUS_API_KEY` and `AMADEUS_API_SECRET` — free-tier Amadeus Self-Service
  API credentials, used by `flights-search`. Without them, flight search falls back to
  Claude's web search.

Nothing else is required. Everything degrades gracefully to web search + paste-a-listing
if you skip the optional API keys.

## 1. Fork and clone

```bash
gh repo fork <you>/ai-holiday-search --clone
cd ai-holiday-search
```

(Or fork via the GitHub UI and `git clone` the usual way.)

## 2. Install dependencies

```bash
uv sync
```

This installs `requests` into a project-local virtualenv; everything else the tooling uses
is Python standard library.

## 3. (Optional) Configure API keys

If you have Amadeus Self-Service API credentials, export them before running Claude Code:

```bash
export AMADEUS_API_KEY=your_key_here
export AMADEUS_API_SECRET=your_secret_here
```

By default the adapter calls Amadeus's test/sandbox host. If you have production
credentials, also set:

```bash
export AMADEUS_HOSTNAME=production   # or a full hostname; defaults to the test host
```

Mismatching credential type and `AMADEUS_HOSTNAME` (e.g. production credentials against
the test host) is a common cause of `401` errors — make sure they match.

Never commit these — put them in your shell profile or a local `.env` file (already
gitignored), not in any tracked file.

## 4. Run `/setup`

```bash
claude
```

Then inside Claude Code:

```
/setup
```

`/setup` auto-detects what you have and offers three modes:

1. **Documents folder** — populate `documents/past-trips/` and `documents/preferences/`
   first (see `documents/README.md`), then run `/setup`. This mode is idempotent: re-run
   it any time you add more material and it will incorporate the new content.
2. **Paste freeform** — paste a description of your travel preferences directly into the
   chat; `/setup` will structure it into a profile.
3. **Interview** — `/setup` asks you a structured set of questions covering who's
   traveling, constraints (home airports, budget, dates, visa situation), style (pace,
   accommodation standard, food priorities), dealbreakers/must-haves, and trip history.

### What lands where

| Location | Tracked in git? | Contents |
| --- | --- | --- |
| `profile/` | No (gitignored) | Your filled-in traveler profile — the authoritative source `/scrape` and `/plan` read from. |
| `documents/past-trips/`, `documents/preferences/` | No (gitignored, except the folder README) | Raw source material you supply for `/setup` to read. |
| `.claude/skills/holiday-planner/01-06*.md` | Yes | Generic templates with `<!-- FILL IN -->` markers, describing the shape of profile fields. Not your real data. |
| `itineraries/` | No (gitignored) | Output of `/plan`, one folder per trip. |
| `watchlist/` | No (gitignored) | State written by `/watch` — trip snapshots and price history. |
| `trip_scraper/` | No (gitignored) | Scraper state — seen trips, dedup cache. |
| `trip_tracker.csv` | No (gitignored) | Your personal shortlist spreadsheet, created from `trip_tracker.csv.example`. |

## 5. Search and plan

```
/scrape
/plan Lisbon, 5 nights in March
```

See the main [README.md](README.md) for the full command reference and workflow details.

## 6. Adding a search source

Search adapters live in `.agents/skills/`. To add a new one (e.g. a local charter
operator or booking site):

1. Copy an existing folder, e.g.:
   ```bash
   cp -r .agents/skills/packages-search .agents/skills/my-operator-search
   ```
2. Edit `SKILL.md` to describe the new source and its result format.
3. Edit `search.py` (or your CLI's entry point) to point at the new site or API, keeping
   the same `--json` / `--help` / non-zero-exit-on-failure contract as the other adapters.
4. Reference the new source from `/scrape`'s configured sources or `search-queries.md` as
   needed.

PRs adding country- or region-specific package/charter skills are welcome.

## 7. Scheduling `/watch`

`/watch` re-checks saved trips and reports price drops, rises, and sold-out warnings. Run
it manually, or schedule it:

- **cron** (local machine):
  ```cron
  0 8 * * * cd /path/to/ai-holiday-search && claude -p "/watch"
  ```
- **CI** (e.g. GitHub Actions scheduled workflow) — note this requires committing any
  watchlist state you want persisted between runs, which conflicts with the
  gitignore-personal-data rule; running `/watch` on a personal machine or a private
  scheduled job is the recommended approach instead of a public CI schedule.
- **Claude Code recurring task** — if your Claude Code setup supports scheduled/looping
  invocations, point it at `/watch` on your preferred interval.

## Troubleshooting

**`/scrape` or `/plan` says to run `/setup` first.**
`profile/` doesn't exist yet, or is missing required fields. Run `/setup`.

**Flight search silently falls back to web search.**
`AMADEUS_API_KEY`/`AMADEUS_API_SECRET` aren't set, or the Amadeus API call failed. Check
your environment variables; the CLI never prints secrets, so check exit codes/status
messages rather than expecting key values in output.

**`git status` shows profile/personal files as untracked-but-should-ignore.**
Confirm you haven't renamed a gitignored folder or added files outside the patterns in
`.gitignore`. Run `git check-ignore -v <path>` to debug why a given file is or isn't
ignored.

**A search source CLI exits non-zero.**
Run it directly with `--help` and check its documented failure modes in its `SKILL.md` —
adapters are designed to fail loudly rather than return silently empty results.

**I want to start over.**
```
/reset profile    # clears profile files, preserves framework rules
/reset watchlist  # clears saved trips and price history
/reset all        # both
```
`/reset` always shows what will be deleted and requires typing `RESET` to confirm.
