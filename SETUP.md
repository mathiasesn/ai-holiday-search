# Setup guide

This guide covers getting **ai-holiday-search** running end to end, via either
distribution route: an installed Claude Code plugin, or a fresh fork/clone.

## Which route should I use?

| | Plugin install | Fork/clone |
| --- | --- | --- |
| When to use it | You just want to use the framework | You want to modify commands, skills, or add a search source |
| Where your data lives | `~/.ai-holiday-search/` (one profile, shared across every project) | Inside the repo checkout (gitignored) |
| Setup effort | Two `/plugin` commands, no clone | `gh repo fork` + `git clone` |
| Works from a downloaded ZIP or a Windows checkout without symlink support | Yes | No — see the note in step 1 |

Both routes run the identical five commands and the same two Playwright MCP servers.

## Prerequisites

- [Claude Code](https://claude.com/claude-code) (CLI)
- [uv](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`,
  or via Homebrew/pipx/winget (see the
  [installation guide](https://docs.astral.sh/uv/getting-started/installation/)). uv
  provisions its own Python, so a system Python install is not required — it will fetch
  Python 3.10+ (the project's minimum supported version) automatically if needed.
- (Optional) `AMADEUS_API_KEY` and `AMADEUS_API_SECRET` — free-tier Amadeus Self-Service
  API credentials, used by `flights-search`. Without them, flight search falls back to
  Claude's web search.
- (Optional) The [Claude Chrome extension](https://claude.ai/chrome) — enables the three
  browser-driven sources, `trivago-search` (stays), `momondo-search` (flights, stays, and
  packages), and `booking-search` (stays and flights — booking.com has no packages
  product). These drive your own signed-in Chrome session because none of these sites has a
  usable API. They need no credentials and never log in, book, or pay. You will be asked
  to grant per-site permission the first time. Without the extension, `/scrape` falls back
  to web search.
- **Node.js (`npx`)** — lets Claude Code start the two Playwright MCP servers declared in
  this repo's tracked `.mcp.json`. The headless one is the second way to reach the same
  three browser-driven sources, and the only way to reach them *unattended*, so it is what
  makes a scheduled `/watch` cover them (§7). `/scrape` can opt into it too, though it
  defaults to the Chrome extension. Without Node the servers fail to start and both
  commands fall back to their non-browser paths — nothing breaks. `ARCHI.md` §7 documents
  both servers' arguments and the headed-debugging recipe.

Nothing else is required. Everything degrades gracefully to web search + paste-a-listing
if you skip the optional API keys and the extension.

## 1. Install: plugin, or fork and clone

### Option A — Plugin install (recommended)

Inside Claude Code:

```
/plugin marketplace add mathiasesn/ai-holiday-search
/plugin install ai-holiday-search
```

This needs `.claude-plugin/` present on the repo's default branch — as of this writing it
only exists on an unmerged branch, so the command above currently fails with `Error:
Marketplace file not found at .../.claude-plugin/marketplace.json`. Until it's merged, you
can install from a local checkout instead:

```
/plugin marketplace add /path/to/ai-holiday-search
/plugin install ai-holiday-search@ai-holiday-search
```

This fallback is a *directory-source* install — see the warning below for what that means
before you use it.

The repo is its own marketplace (`.claude-plugin/marketplace.json`), so this needs no
separate registry. Once installed, the plugin's top-level `commands/`, `skills/`, and
root `.mcp.json` are auto-discovered — the same five slash commands and the same two
Playwright MCP servers as clone mode, with nothing to configure. Skip to step 3 (dependency
install is only needed for clone mode, since the plugin's Python adapters run via `uv run`
against their own PEP 723 headers regardless).

Installed commands register namespaced — `/ai-holiday-search:setup`,
`/ai-holiday-search:scrape`, and so on — not the bare `/setup` shown elsewhere in this
guide. On the Claude Code version this was tested on, typing the bare form still resolved
correctly via fuzzy matching, but that's an observed convenience, not the command's real
name in plugin mode; the namespaced form is what's actually registered. (In clone mode the
bare form is the real name.)

**Directory-source installs copy your whole working tree, gitignored files included.**
Adding a marketplace from a local path (as above) is a "directory source": Claude Code
makes a real copy of the checkout — not a symlink — at
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, and that copy includes
whatever gitignored personal state exists in the checkout at install time: `profile/`,
`watchlist/`, `trip_scraper/`, `documents/`, `itineraries/`, `trip_tracker.csv`,
`.claude/settings.local.json`, and `.playwright-mcp/` (which, per `ARCHI.md` §9, can
contain the runner's public IP). This only affects local-path (directory-source) installs
— a GitHub-source install carries only tracked files and is unaffected. If you installed
from a local path, remove the cached copy with
`rm -rf ~/.claude/plugins/cache/<marketplace>`. Tracked as
[issue #22](https://github.com/mathiasesn/ai-holiday-search/issues/22).

### Option B — Fork and clone

```bash
gh repo fork <you>/ai-holiday-search --clone
cd ai-holiday-search
```

(Or fork via the GitHub UI and `git clone` the usual way.)

Use this route if you want to modify the framework itself — edit commands, skills, or add
a search source.

**Windows / ZIP-download limitation.** Clone mode relies on `.claude/commands` and
`.claude/skills` being tracked symlinks into the top-level `commands/`/`skills/`
directories. Symlinks don't survive a Windows checkout unless symlink support is enabled
(`git config core.symlinks true`, or Developer Mode) or GitHub's "Download ZIP" button —
both flatten symlinks into broken files or plain text. If you hit this, either use the
plugin install instead, or re-clone with `git config --global core.symlinks true` set
*before* cloning (an already-broken checkout needs a fresh `git clone` to pick this up).

## 2. Install dependencies (clone mode only)

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
/ai-holiday-search:setup
```

(Plugin installs register commands namespaced like this; see step 1. In clone mode, or if
fuzzy matching resolves it for you, the bare `/setup` shown throughout the rest of this
guide works too.)

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

Every command resolves two roots before touching a file: `FRAMEWORK_ROOT` (where the
tracked command/skill Markdown lives) and `DATA_ROOT` (where your personal profile and
generated state live). In clone mode both are the repo root; in plugin mode
`FRAMEWORK_ROOT` is the plugin's installed location and `DATA_ROOT` is
`~/.ai-holiday-search`. The table below shows clone-mode paths; in plugin mode, read every
`DATA_ROOT`-rooted row as `~/.ai-holiday-search/<same path>` instead.

| Location | Tracked in git? | Contents |
| --- | --- | --- |
| `profile/` (`DATA_ROOT`) | No (gitignored in clone mode; outside the repo entirely in plugin mode) | Your filled-in traveler profile — the authoritative source `/scrape` and `/plan` read from. |
| `documents/past-trips/`, `documents/preferences/` (`DATA_ROOT`) | No (gitignored, except the folder README) | Raw source material you supply for `/setup` to read. In plugin mode, drop files in `~/.ai-holiday-search/documents/past-trips/` and `.../preferences/`. |
| `skills/holiday-planner/01-06*.md` (`FRAMEWORK_ROOT`) | Yes | Generic templates with `<!-- FILL IN -->` markers, describing the shape of profile fields. Not your real data. |
| `itineraries/` (`DATA_ROOT`) | No (gitignored) | Output of `/plan`, one folder per trip. |
| `watchlist/` (`DATA_ROOT`) | No (gitignored) | State written by `/watch` — trip snapshots and price history. |
| `trip_scraper/` (`DATA_ROOT`) | No (gitignored) | Scraper state — seen trips, dedup cache. |
| `trip_tracker.csv` (`DATA_ROOT`) | No (gitignored) | Your personal shortlist spreadsheet, created from `trip_tracker.csv.example`. |

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
   Keep the `# /// script ... # ///` PEP 723 header at the top of `search.py` — it's what
   lets `uv run` execute the copied file standalone; extend its `dependencies` list if the
   new source needs packages beyond `requests`.
4. Reference the new source from `/scrape`'s configured sources or `search-queries.md` as
   needed.

### Browser-driven sources

If a site has no usable API and blocks non-browser clients, the alternative is a
Markdown-only skill under `skills/` with no `search.py` and no exit code —
`trivago-search`, `momondo-search`, and `booking-search` are the three worked examples. Such a skill defines its
own fallback chain instead of the adapter exit-code protocol, and normalizes into the same
result record. Verify any URL grammar against the live site rather than guessing it, record
the date you captured it, and mark anything you couldn't confirm as unverified. `ARCHI.md`
§8 documents both paths in full.

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

Scheduling covers browser-driven trips too, not just the API adapters. `/watch` re-checks
`trivago-search`, `momondo-search`, and `booking-search` trips through the headless
Playwright MCP server in `.mcp.json`, which needs no attended session and no site
permission. Confirmed on 2026-07-26 by an on-demand run that read a live trivago price
headlessly; the *scheduled* path itself (cron, CI, recurring task) has not been exercised
yet — see [issue #8](https://github.com/mathiasesn/ai-holiday-search/issues/8).

Two things to expect from unattended browser reads. Sites can block them: trivago rejects
headless Chrome's default User-Agent, which is why the tracked `.mcp.json` overrides it.
And a blocked or challenged read is recorded as *could not verify*, reported separately
from a sold-out warning, and never overwrites the last known good price.

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

**`/scrape` never seems to use trivago, momondo, or booking.com.**
The Chrome extension isn't installed or connected, or you haven't granted permission for
that site. All three sources degrade silently to web search by design, so the run still
completes — `/scrape` reports which sources used a live read versus a fallback, so check
there to confirm.

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
