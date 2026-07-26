# AI Holiday Search — Architecture Documentation

> Generated: 2026-07-26 · Commit: 1c464c3 · Version: 0.1.0 (from `pyproject.toml`; no git tags exist)
> Last architecture change: `1c464c3` — Playwright MCP added as a second, unattended-capable browser driver, with its trivago bot-block fix (tracked `.mcp.json`, `profile/tooling.md` driver preference, browser-driven `/watch` re-check branch)
> Re-read this file at the start of any session touching this codebase. Update it when the architecture changes (new major dependency, restructured layer, changed convention).

---

## 1. How to Read This Document

This is the structural source of truth for `ai-holiday-search`: what exists, where it lives, how the pieces compose, and which conventions are enforced by tooling.

**It is deliberately complementary to `CLAUDE.md`, not a replacement.** `CLAUDE.md` (tracked, repo root) is the authority on *behavioral* rules — how fit scoring must be presented, that pacing rules are hard constraints, that uncertainty must be flagged, that personal data must never be committed. This document does not restate those rules and must never contradict them. When the two appear to disagree, `CLAUDE.md` wins on behavior; this file wins on structure.

Read sections 2–4 to orient, 8–10 for the parts of this repo that cannot be guessed from the file tree (the adapter contract, the data boundary, and how the prompt layer composes), and section 12 for the non-negotiables.

Known gaps, deferred decisions, and engineering debt are tracked in `BACKLOG.md` at the repo root — consult it before "fixing" something that looks broken, since several apparent problems (notably the adapter code duplication) are deliberate and documented there.

---

## 2. Overview

`ai-holiday-search` is a **Claude Code framework template**, not a conventional application. It is meant to be forked: a traveler runs `/setup` to write a local, gitignored profile, then uses `/scrape`, `/plan`, and `/watch` to find, plan, and price-track holidays. `/reset` wipes local state.

Two layers make up the system, and the balance between them is the single most important thing to understand:

1. **The prompt/agent layer is the product.** Most of the repo's substance is Markdown that Claude Code reads as instructions: 5 slash commands, 5 Claude skills, and 6 numbered holiday-planner reference documents. Workflow logic — fit scoring math, pacing enforcement, the drafter–reviewer pipeline, budget rules, JSON state-file schemas — lives in prose and tables in these files, not in Python.
2. **The Python layer is thin support.** ~1,100 lines total, split between three near-standalone search adapters (`.agents/skills/*/search.py`) that wrap external APIs, and two repo-hygiene scripts (`tools/lint_skills.py`, `tools/security_guards.py`) that CI runs on every push.

Architecturally, the flow is: `/setup` fills `profile/` from tracked templates → `/scrape` fans out to adapters (or falls back to web search), normalizes and deduplicates results, and scores them → `/plan` runs a 7-step drafter–reviewer pipeline producing a verified Markdown itinerary → `/watch` snapshots trips and re-checks prices over time.

A defining constraint: **every external-data path degrades gracefully.** No adapter is required; missing credentials fall back to Claude's own web search, and any bot-blocked site falls back to the user pasting listing text into chat. A fresh clone with zero API keys is fully functional.

---

## 3. Technology Stack

| Component | Choice | Notes |
|---|---|---|
| Primary "language" | Markdown (agent instructions) | The bulk of the system's logic |
| Python | `>=3.10` (`pyproject.toml`), pinned to `3.12` for dev (`.python-version`) | CI matrixes 3.10 and 3.12 for adapters only |
| Package/env manager | **uv** | Sole supported path; `[tool.uv] package = false` (this is not an installable package) |
| Lockfile | `uv.lock` (committed) | Covers `tools/` + project deps, **not** the adapters — see §8 |
| Runtime dependency | `requests` | The only third-party **Python** dependency, used solely by the adapters. Node/`npx` + `@playwright/mcp@0.0.78` is a separate, non-Python runtime prerequisite for the `/watch` browser path (and the `/scrape` Playwright opt-in) — see the row below |
| Tooling dependencies | none | `tools/*.py` are stdlib-only by design, including a hand-rolled YAML-frontmatter parser |
| CI | GitHub Actions (`.github/workflows/ci.yml`) | 3 jobs; `astral-sh/setup-uv@v5` |
| Host agent | Claude Code | Commands, skills, and subagent (`Task`/`Agent`) spawning |
| Optional external API | Amadeus Self-Service (flights) | Free tier; stays/packages ship without a bundled API |
| Optional browser drivers | `claude-in-chrome` MCP tools, Playwright MCP | Only for browser-driven sources (§8). Either can run all three (trivago/momondo/booking). `/scrape` defaults to `claude-in-chrome` (attended, per-site permission); `/watch` defaults to Playwright (the only one that runs unattended). Preference resolved via `profile/tooling.md` (§9); absent ⇒ caller default. Neither present ⇒ web-search fallback |
| MCP server | Two Playwright servers, declared in tracked `.mcp.json` | `playwright` — headless, for unattended/cron runs. `playwright-headed` — same version, visible browser, for attended debugging. Both isolated (fresh profile, no persisted cookies) per run. **§7 owns both argument lists** |

There is no test framework, no linter config, and no formatter config in this repo. `tools/lint_skills.py` is a bespoke structural linter, not a Python style linter. Adding real tests is `BACKLOG.md` item 1.

---

## 4. Project Structure

```
ai-holiday-search/
├── CLAUDE.md                       # Behavioral rules for Claude in this repo — authority on behavior
├── ARCHI.md                        # This file — architecture memory, authority on structure
├── README.md                       # User-facing guide (fork → setup → scrape → plan → watch)
├── SETUP.md                        # Detailed install/prereq guide
├── BACKLOG.md                      # Known debt + deferred decisions; read before "fixing" oddities
├── pyproject.toml                  # name/version, requires-python >=3.10, deps=[requests], package=false
├── uv.lock                         # Committed lock for the project env (NOT the adapters)
├── .python-version                 # 3.12 — dev pin uv provisions
├── .gitignore                      # Encodes the personal-data boundary (see §9)
├── .mcp.json                       # Tracked MCP config: headless + headed Playwright servers (§7)
├── trip_tracker.csv.example        # Header-only template; /setup copies it to gitignored trip_tracker.csv
│
├── .claude/                        # Claude Code layer (host-specific)
│   ├── commands/                   # 5 slash commands, one .md each — the user-facing entry points
│   │   ├── setup.md  scrape.md  plan.md  watch.md  reset.md
│   ├── skills/                     # Reference knowledge the commands load
│   │   ├── holiday-planner/        # SKILL.md + 01-…-06-*.md: profile shape, scoring, pacing, budget, packing
│   │   ├── trip-scraper/           # SKILL.md (adapter protocol + state schemas) + search-queries.md
│   │   ├── price-watch/            # SKILL.md: slug derivation, watchlist schema, re-check thresholds
│   │   ├── trivago-search/         # SKILL.md: browser-driven stays source, no search.py, own fallback chain
│   │   ├── momondo-search/         # SKILL.md: browser-driven flights/stays/packages source, no search.py, own fallback chain
│   │   └── booking-search/         # SKILL.md: browser-driven stays/flights source, no search.py, own fallback chain
│   └── settings.local.json         # Per-user permissions; untracked — see BACKLOG item 4
│
├── .agents/skills/                 # Agent-AGNOSTIC search adapters — designed to be copied out wholesale
│   ├── flights-search/             # SKILL.md + executable search.py (Amadeus)
│   ├── stays-search/               # SKILL.md + executable search.py (generic configurable JSON feed)
│   └── packages-search/            # SKILL.md + executable search.py (template for local operators)
│
├── tools/                          # Repo-hygiene scripts run by CI — stdlib only, never copied into adapters
│   ├── _repo.py                    # Shared git helpers (repo_root, tracked_files, ignored_paths)
│   ├── lint_skills.py              # Frontmatter, link, structure, and adapter-contract validation
│   └── security_guards.py          # Secret scanning + personal-data leak detection
│
├── .github/workflows/ci.yml        # lint-and-guards | adapter-smoke (3.10,3.12) | standalone-adapter
│
├── documents/                      # INPUT for /setup — past-trips/ and preferences/ (contents gitignored)
├── profile/                        # GENERATED by /setup — the real traveler profile (gitignored, absent in a fresh clone); includes tooling.md (§9)
├── itineraries/                    # GENERATED by /plan — one folder per trip (gitignored)
├── watchlist/                      # GENERATED by /watch — one JSON per watched trip (gitignored)
├── trip_scraper/                   # GENERATED by /scrape — seen.json dedupe state (gitignored)
└── specs/                          # Local working specs; specs/.gitignore contains `*` — deliberately untracked
```

**Two skills directories, and the distinction matters.** `.claude/skills/` holds Claude-Code-specific planning knowledge that assumes the whole repo is present. `.agents/skills/` holds portable, agent-agnostic search adapters that must work when a single folder is copied elsewhere with nothing else — this constraint drives several design decisions in §8.

---

## 5. Core Architecture Principles

These are the principles actually governing this codebase, inferred from the code and confirmed by its comments and `BACKLOG.md`:

1. **Logic lives in Markdown; Python is I/O only.** Scoring, pacing, budgeting, and pipeline sequencing are specified in `.claude/skills/**`. Do not port that logic into Python — the agent is the interpreter. Python exists only where a deterministic external call or a hygiene check is needed.
2. **Graceful degradation is mandatory, never optional.** Every source has a fallback chain, whatever its kind: adapter (exit 2) or browser read (unreachable, permission denied, bot challenge) → Claude web search → user pastes text. The paste path is a first-class input that enters the same evaluate → draft → review → verify pipeline, per `CLAUDE.md`. No source may fail a `/scrape` run.
3. **Adapters are self-contained, and duplication is the accepted price.** The copy-a-folder fork workflow means `.agents/skills/*/search.py` cannot import a shared module. ~330 near-identical lines across the three adapters is a **deliberate, rejected-refactor** decision (`BACKLOG.md` item 7), guarded by a CI drift check instead of deduplicated.
4. **Personal data never enters git.** Enforced structurally by `.gitignore` and mechanically by `tools/security_guards.py`, not by convention alone. See §9.
5. **Tracked templates are the *shape*, never the data.** `.claude/skills/holiday-planner/0X-*.md` carry `<!-- FILL IN -->` markers and generic defaults. A filled `profile/0X-*.md` copy always wins when present; if `profile/` is absent, commands must stop and say "run `/setup`" rather than plan against placeholder examples.
6. **One authority per schema.** Each shared data shape is defined in exactly one file, and everything else points back to it. `.claude/skills/trip-scraper/SKILL.md` is authoritative for the adapter result record, the no-credentials protocol, the normalized candidate record, and `seen.json`. `.claude/skills/price-watch/SKILL.md` is authoritative for the watchlist schema. Adapter `SKILL.md`s and Python docstrings only summarize and link back.
7. **Guards must fail loudly, never silently pass.** Both `tools/` scripts treat "could not determine the answer" (e.g. a git failure) as a hard error. This is scar tissue: two guards previously passed unconditionally while checking nothing (documented in `BACKLOG.md` item 1).

---

## 6. Build System & Toolchain

There is no build step. Commands below are copied verbatim from `.github/workflows/ci.yml` and the README; the two lint/guard invocations were executed and confirmed green at commit `30f2b77`.

```bash
# Install / sync the project environment (provisions Python too — no system Python needed)
uv sync

# Structural lint: SKILL.md + command frontmatter, relative links, adapter structure & contract
uv run python tools/lint_skills.py

# Secret scanning + personal-data leak detection across tracked files
uv run python tools/security_guards.py

# Run a search adapter (installs `requests` into an isolated per-script env via PEP 723)
uv run .agents/skills/flights-search/search.py --help
uv run .agents/skills/stays-search/search.py --destination Lisbon --check-in 2026-10-12 \
  --check-out 2026-10-19 --guests 2 --json
```

**CI jobs** (`.github/workflows/ci.yml`, on every push and PR):

| Job | What it proves |
|---|---|
| `lint-and-guards` | `uv sync`, then both `tools/` scripts exit 0. Runs only on the `.python-version` pin (3.12) — see `BACKLOG.md` item 9. |
| `adapter-smoke` | Each adapter's `--help` succeeds on Python 3.10 **and** 3.12, with all credential env vars unset. Uses `uv run --python X`, which fails rather than silently falling back to the pin. |
| `standalone-adapter` | Each adapter folder is copied to a `mktemp -d` outside the repo and run there. This is the guard on the copy-a-folder fork workflow: a broken PEP 723 header in any adapter must fail here. |

The credential env-var list lives once in the workflow's top-level `env.ADAPTER_CRED_VARS`. **A new adapter credential must be added there**, not per-job.

No tests exist. `BACKLOG.md` item 1 explains why that is the highest-priority gap: CI asserting exit 0 cannot distinguish a working guard from a guard that checks nothing.

---

## 7. Configuration

Adapter configuration is environment variables; there is no adapter-specific config file. Every variable is **optional** — unset means the adapter takes its documented fallback path. The one exception is MCP server configuration: tracked `.mcp.json` at the repo root declares two Playwright MCP servers — see §3.

**`playwright`** (`npx -y @playwright/mcp@0.0.78 --headless --isolated --user-agent "…Chrome/149.0.0.0…"`) is the one the `/watch` browser path (and the `/scrape` Playwright opt-in) depend on. `--headless`: a scheduled/cron run has no display, so a headed browser cannot start there. `--isolated`: a fresh profile per run, no persisted cookies or login state — this is what neutralizes the browser-driven skills' prefilled-previous-search privacy hazard (trivago/momondo/booking all arrive prefilled from account history when a real, logged-in session is used instead). Trade-off: consent/cookie walls appear on every run, which is why the browser-driven skills define an unattended terminal outcome. `--user-agent`: overrides headless Chrome's default UA, which trivago rejects — rationale and per-source scope in `.claude/skills/trivago-search/SKILL.md` ("Why these Playwright flags"), evidence in `BACKLOG.md` item 10.

**`playwright-headed`** (`npx -y @playwright/mcp@0.0.78 --isolated`, no `--headless`) is a second, tracked server for attended debugging with a visible browser window — registered out of the box so `/scrape`'s Playwright opt-in can be run headed without any manual `claude mcp add`. It keeps `--isolated` for the same privacy reason as above, and deliberately carries **no** `--user-agent`: a headed browser advertises no `Headless` token, so there is nothing to override. Point the driver at it for a debugging session, then go back to `playwright` for normal use.

| Variable | Used by | Effect when unset |
|---|---|---|
| `AMADEUS_API_KEY`, `AMADEUS_API_SECRET` | `flights-search` | Exit 2, `reason: missing_api_credentials`, fall back to web search |
| `AMADEUS_HOSTNAME` | `flights-search` | Defaults to `test` → `test.api.amadeus.com`. Accepts `test`, `production`, or a full hostname |
| `STAYS_API_URL`, `STAYS_API_KEY` | `stays-search` | Without `STAYS_API_URL`: exit 2, `reason: no_source_configured`, **no network call at all** |
| `PACKAGES_API_URL`, `PACKAGES_API_KEY` | `packages-search` | Exit 2, `reason: no_operator_configured` |

Secrets go in `.env` (gitignored) or the shell environment. **Adapters must never print, log, or include credentials in error output** — `flights-search` catches broadly and prints only `exc.__class__.__name__` for exactly this reason. `tools/security_guards.py` allowlists these variable *names* appearing in docs but flags any real-looking *value* attached to them.

Planning defaults (destinations, date windows, price ceilings) are configuration too, but they live in Markdown: `.claude/skills/trip-scraper/search-queries.md` is the tracked generic template, overridden by `profile/search-queries.md` when `/setup` has written one.

---

## 8. Search Adapter Contract

This is the least guessable part of the repo and the most important to get right when adding a source.

### Structural requirements

Every directory under `.agents/skills/` must contain a `SKILL.md` (with frontmatter whose `name` **equals the directory name**) and an **executable** `search.py`. `check_agents_skills_structure()` in `tools/lint_skills.py` fails CI on a missing file or a non-`chmod +x` script.

Each `search.py` starts with a PEP 723 inline metadata header:

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
```

This header — not `pyproject.toml` — is what lets `uv run search.py` work in a copied folder outside the repo. `uv run` on a script resolves an isolated env from the inline block and **does not consult `uv.lock`**, so adapter dependencies resolve unpinned on every run (`BACKLOG.md` items 6 and 8; item 8 also notes that nothing currently exercises the header, because `requests` is imported lazily inside `main()` after the no-credentials early return).

### Exit-code protocol

| Code | Meaning | Caller behavior |
|---|---|---|
| `0` | Success — results printed, possibly `[]` | Use the results |
| `2` | **No credentials configured — not a crash** | Fall back to Claude web search with the same query params, normalize identically, continue the run |
| `1` | Genuine failure (bad args, network/HTTP error, bad response) | Report it, skip that source, continue with the others |

On exit 2 with `--json`, the adapter prints **exactly one JSON object**:

```json
{"status": "no_credentials", "reason": "<machine token>", "message": "<human sentence>", "fallback": "web_search", "results": []}
```

`status` is always literally `"no_credentials"`; `fallback` is always `"web_search"`; `results` is always `[]`. `reason` varies per adapter and is **for display only — never branch on it**; branch on the exit code and `status`.

`check_adapter_contract()` in `tools/lint_skills.py` enforces this by actually executing every adapter with credentials stripped from the environment and asserting exit 2, one parseable JSON object, `status`/`fallback` correctness, and an **identical top-level key set across all adapters**. This check is what makes the deliberate duplication (§5.3) safe — if you ever revisit that decision, preserve this check.

### Result record

`--json` on the success path prints a JSON **array** of records; `[]` when there are no matches. Authoritative definition in `.claude/skills/trip-scraper/SKILL.md`:

`source` (str, adapter name) · `title` (str) · `url` (str|null) · `price` (float, total) · `currency` (str, ISO) · `price_per_person` (float) · `dates` (dict: `{depart, return}` for flights/packages, `{check_in, check_out}` for stays) · `details` (dict, free-form source-specific).

This is **distinct from** the "normalized candidate record" that `trip-scraper` builds by merging adapter records with destination/trip context before scoring.

**Carve-out: a source may instead be browser-driven** (lives in `.claude/skills/`, Markdown-only, no `search.py`/exit code, its own fallback chain) — the exit-code protocol above remains load-bearing and unchanged for CLI adapters; this only exempts browser-driven sources from it. Such a source may cover one vertical or several, in which case which verticals run is query-driven per the "Vertical selection" rule in `.claude/skills/trip-scraper/SKILL.md`; the current instances are listed in the directory tree above.

### Adding a new source

**CLI adapter:** copy an existing adapter folder, rename it, update `SKILL.md` frontmatter `name` to match the new directory, point `search.py` at your API, keep the exit-code protocol and result-record shape exactly, add any new credential env vars to `ADAPTER_CRED_VARS` in the CI workflow and to `ALLOWED_ENV_VAR_NAMES` in `tools/security_guards.py`, and `chmod +x search.py`. Do not introduce a shared import.

**Browser-driven source:** add a Markdown-only skill under `.claude/skills/` — no `search.py`, no exit code. Define its own fallback chain, normalize results into the same result record as CLI adapters, and register it in both `search-queries.md`'s source table and `trip-scraper`'s fan-out step. If it covers more than one vertical, register it in each vertical's fan-out list and follow the "Vertical selection" rule rather than restating it. Verify any URL grammar against the live site, record the date, and mark unverified tokens as such — `BACKLOG.md` item 11 explains why this date is the only freshness signal available.

---

## 9. Data Boundary & Privacy Model

The repo is split into **tracked framework content** and **untracked personal data**, and this split is enforced by tooling, not trust.

**Tracked (safe to commit):** `CLAUDE.md`, `ARCHI.md`, `README.md`, `SETUP.md`, `BACKLOG.md`, everything under `.claude/commands/`, `.claude/skills/`, `.agents/skills/`, `tools/`, `.github/`, `pyproject.toml`, `uv.lock`, `.mcp.json`, `trip_tracker.csv.example`, and the `.gitkeep` / `documents/README.md` scaffolding placeholders.

**Gitignored (never commit):** `profile/`, `itineraries/*`, `watchlist/*`, `trip_scraper/*`, `trip_tracker.csv`, the contents of `documents/past-trips/` and `documents/preferences/`, `.env`, `*.key`, `.playwright-mcp/` (Playwright MCP's console logs and page snapshots of real searches, which include the runner's public IP), and `specs/` (via its own `.gitignore` containing `*`).

**`profile/tooling.md`** — the browser-driver preference, written by `/setup`, read by `/scrape` (and `/watch`). Shape:

```
driver:
  scrape: claude-in-chrome   # or: playwright
  watch: playwright          # or: claude-in-chrome
```

Absence of the file, or of either field, means the caller default applies silently (`/scrape` →
`claude-in-chrome`, `/watch` → Playwright) — never an error, never the "run `/setup`" precondition.
Covered by `profile/` in `.gitignore`, so it is never committed. **Not a seventh numbered
`holiday-planner` template** — it holds a tooling knob (which MCP driver executes a browser read),
not traveler data, and must never be merged into the six numbered profile files or their templates.

`tools/security_guards.py` runs three checks over `git ls-files`:

1. **Secret patterns** — regex for `NAME=value` / `NAME: value` where `NAME` ends in `API_KEY|API_SECRET|SECRET|TOKEN|PASSWORD|ACCESS_KEY`, plus private-key blocks. Placeholder values (`<value>`, `your_key_here`, quoted templates) are allowed. A *documented* env-var name with a real-looking value attached is still flagged.
2. **No tracked file under a personal path** — asks git directly rather than restating `.gitignore` prefixes.
3. **`.gitignore` coverage** — probes representative sample paths (`profile/some-file.md`, `.env`, …) via `git check-ignore`.

**Two git subtleties in `tools/_repo.py` that you must not undo** (both were real bugs, documented in `BACKLOG.md` item 1):

- `ignored_paths(..., no_index=True)` is **required** when asking about *tracked* paths. Without `--no-index`, `git check-ignore` reports nothing for a tracked file (tracking beats `.gitignore`), so the leak check would pass unconditionally and catch nothing — which is exactly the leak it exists to catch.
- `git check-ignore -v` reports the **last** matching pattern, *including negations*. `ignored_paths` skips patterns starting with `!`, otherwise every deliberately-tracked `.gitkeep` and `documents/README.md` is misreported as a leak.

Guards currently run in CI only, i.e. after a leak has already reached the remote. Installing them as a pre-commit hook is `BACKLOG.md` item 2.

Per `CLAUDE.md`: **never `git add -A` in this repo.** Check `git status` first and flag anything that looks personal before staging.

---

## 10. Command & Skill Layer

### How the layers compose

```
User types /scrape
   → .claude/commands/scrape.md          (the procedure: inputs, steps, outputs, state touched)
       → .claude/skills/trip-scraper/    (fan-out rules, adapter protocol, dedupe, schemas)
           → .agents/skills/*/search.py       (the network call, or exit 2 → web-search fallback)
           → .claude/skills/trivago-search/   (browser read, or own fallback chain → web search)
           → .claude/skills/momondo-search/   (browser read across flights/stays/packages, or own fallback chain → web search)
           → .claude/skills/booking-search/   (browser read across stays/flights, or own fallback chain → web search)
       → .claude/skills/holiday-planner/03-trip-evaluation.md  (scoring + ranking)
       → profile/*.md                     (the traveler's real data; must exist)
```

Commands are procedure; skills are reference. A command file states its inputs, the state it reads and writes, and numbered steps. A skill file defines schemas, rules, and formats that multiple commands share.

### Frontmatter conventions (enforced by `tools/lint_skills.py`)

- **`SKILL.md`** (both skill trees) requires non-empty `name` and `description`, and `name` **must equal the parent directory name**.
- **`.claude/commands/*.md`** requires a non-empty `description`; they also carry `argument-hint` and `allowed-tools` by convention (not linted).
- **All relative Markdown links must resolve**, as must any backticked repo-relative path ending in `.md`/`.py` that contains a `/` — except paths under gitignored personal directories, which are runtime paths and are skipped. Placeholder notation (`<name>`, `foo/*.md`) is intentionally not matched by the literal-path regex, so new doc notations don't require a linter change.
- The frontmatter parser is hand-rolled (no PyYAML): flat `key: value` scalars only, with quote stripping and wrapped-line continuation.

### The five commands

| Command | Reads | Writes | Shape |
|---|---|---|---|
| `/setup` | `documents/`, `$ARGUMENTS`, holiday-planner templates | `profile/01…06-*.md`, `profile/tooling.md`, `trip_tracker.csv` | 3 modes (documents / pasted text / interview), auto-detected; asks rather than picking silently; documents-mode is idempotent and merges; seeds `tooling.md` with caller defaults and asks before overwriting an existing one |
| `/scrape` | `profile/`, `profile/tooling.md` (optional, driver preference), `search-queries.md`, adapters, `trivago-search/SKILL.md`, `momondo-search/SKILL.md`, `booking-search/SKILL.md`, `trip_scraper/seen.json` | `trip_scraper/seen.json` | Fan out (including browser-driven `trivago-search`, `momondo-search`, and `booking-search` runs via `claude-in-chrome` or Playwright MCP tools, per `tooling.md`, both in its `allowed-tools`; `momondo-search` and `booking-search` each cover whichever of their verticals the run calls for) → normalize → dedupe → score → present sorted by fit with per-criterion reasoning |
| `/plan` | `profile/`, holiday-planner 03/04/05 | `itineraries/<trip-slug>/itinerary.md` | 7 explicit steps, see below |
| `/watch` | `watchlist/*.json`, `profile/tooling.md` (optional, driver preference), adapters, `trivago-search/SKILL.md`, `momondo-search/SKILL.md`, `booking-search/SKILL.md` | `watchlist/<slug>.json` | `add` / `remove` / no-args re-check; dispatches on trip kind — adapter-backed, pasted, or browser-driven (using the unattended Playwright MCP driver by default, per `tooling.md`) |
| `/reset` | — | deletes `profile/`, `watchlist/`, `trip_tracker.csv` | Requires typing `RESET`; touches only gitignored state |

### The `/plan` pipeline

Seven steps, executed explicitly and in order — never skipped, reordered, or merged:

1. **Parse** — destination request or pasted listing text.
2. **Evaluate fit** — score against the profile; **stop and refuse to proceed if `profile/` is missing or still contains `<!-- FILL IN -->`**. If the fit is poor, say so up front, name the violated criteria, and get user confirmation before spending drafting effort.
3. **Draft** — day-by-day plan + budget table, kept in scratch, not shown to the user yet.
4. **Review** — spawn a subagent (`Task`, called `Agent` in some builds) with a **fresh context that has not seen the planning conversation**. It receives only the draft, destination, and dates, and independently researches weather norms, opening hours, local events, scams/tourist traps, and travel-leg feasibility. Run in the foreground; wait for its findings.
5. **Revise** — address every finding, or explicitly justify keeping something as-is.
6. **Verify** — budget rows sum; no day breaks pacing limits; every named venue confirmed to exist via search; travel legs feasible. **Any failure loops back to step 5** — never present an unverified plan.
7. **Present** — write Markdown to `itineraries/<trip-slug>/itinerary.md` and echo it, including the completed checklist, a booking to-do list, and carried-over uncertainty flags.

### The holiday-planner reference files

`01-traveler-profile.md` (group, constraints, budget range, home airports) · `02-travel-style.md` (pace, standards, dealbreakers) · `03-trip-evaluation.md` (scoring) · `04-itinerary-templates.md` (day/trip output templates, pacing limits) · `05-budget-rules.md` (categories, buffer, currency) · `06-packing-and-prep.md`.

Three of these encode hard numbers worth knowing:

- **Scoring** (`03`): weighted sum, weights summing to 100 — style 30, budget 25, travel time 20, season 15, group 10. Bands: 85–100 excellent, 70–84 good, 50–69 workable, 30–49 poor, 0–29 bad. **A dealbreaker violation caps the total at 25, or disqualifies entirely (score 0) if safety- or accessibility-related** — checked *before* the weighted sum, so a cheap dealbreaker-violating trip always ranks below a pricier fitting one. Per-criterion reasoning must always be shown.
- **Pacing** (`04`): default max 2 anchor activities/day (1 with young kids); ≥1 unplanned day per 5 nights; ~30 min max transit between consecutive activities; no anchors on travel days exceeding ~4h door-to-door; at most one pre-09:00 start per day. These numeric limits are defaults that `/setup` tunes per traveler.
- **Budget** (`05`): required buffer of ≥10% of subtotal as its own line item (15% when multiple categories are estimated); every line labeled per-person or group total; EUR primary with DKK noted when relevant; every non-quoted figure explicitly labeled an estimate.

**Output is Markdown only.** Never generate or offer a PDF.

### State file schemas

Both are versioned with `schema_version: 1` and are defined authoritatively in their skill files.

- **`trip_scraper/seen.json`** — `{schema_version, entries}` keyed by `sha256(f"{source}|{destination_slug}|{depart_date}|{return_date}|{price_bucket}")`, where `price_bucket` is the price floored to the nearest 50 so minor fare noise doesn't create false-new entries. `first_seen` is written once; `last_seen` updates every sighting. A candidate is dropped as a duplicate only if the key exists **and** the price hasn't moved buckets — a bucket change is a legitimate price-change re-surface.
- **`watchlist/<slug>.json`** — slug is `{destination-slug}-{depart}-{return}`, with a source tag appended on collision. `original_snapshot` is written once at `/watch add` and **never modified**; `price_history` is append-only, one entry per re-check. Comparison is against the **most recent** entry, not the original. Thresholds: ≥5% down = drop, ≥5% up = rise, within ±5% = unchanged (still recorded), no matching listing = `available: false` + sold-out warning (keep watching; never auto-remove).

---

## 11. Conventions for Making Changes

- **Adding a search source** → §8, "Adding a new source". Never add a shared import under `.agents/skills/`.
- **Adding a slash command** → new `.md` in `.claude/commands/` with a non-empty `description` in frontmatter; state inputs, "State touched", and numbered steps, matching the existing files' shape.
- **Adding a skill** → new directory under `.claude/skills/` containing `SKILL.md` whose frontmatter `name` matches the directory name.
- **Changing a shared schema** → edit the one authoritative file (§5.6) and update the summaries pointing at it. Nothing currently verifies command-vs-skill schema agreement (`BACKLOG.md` item 3), so this is manual and easy to drift.
- **Changing behavioral rules** → those live in `CLAUDE.md` and the holiday-planner files, not here.
- **Before committing** → run both `tools/` scripts, and `git status` before staging. Never `git add -A`.

---

## 12. Summary & Key Architectural Decisions

Non-negotiables — an agent working in this repo must not violate these:

- **Never commit personal data.** `profile/`, `itineraries/`, `watchlist/`, `trip_scraper/`, `trip_tracker.csv`, `documents/` contents, `.env`. Check `git status` before staging; never `git add -A`.
- **Never plan against the tracked templates.** If `profile/` is missing or still has `<!-- FILL IN -->` markers, stop and tell the user to run `/setup`.
- **The adapter exit-code protocol is load-bearing.** Exit 2 means "no credentials, fall back to web search," not failure. The exact no-credentials JSON shape is identical across all adapters and is CI-enforced. It binds every `.agents/skills/*` CLI adapter; browser-driven sources are exempt and carry their own fallback chain instead (§8 carve-out) — that exemption is not a licence to weaken it for adapters.
- **Adapter duplication is deliberate.** Do not extract `.agents/skills/_common.py` — it breaks the copy-a-folder fork workflow. See `BACKLOG.md` item 7 before touching this.
- **Adapters must stay standalone.** Keep the PEP 723 header accurate and never import from `tools/` or across skill folders.
- **Never leak credentials into output.** Errors report exception class names, not messages containing request details.
- **`/plan`'s 7 steps run in order, and step 6 verification can reject.** The reviewer subagent must get fresh context with no sight of the planning conversation.
- **Dealbreakers override score.** Cap at 25 or disqualify at 0; a cheap violating trip never outranks a pricier fitting one.
- **Pacing limits are hard constraints**, enforced by `/plan`'s verification, not suggestions for the user to notice.
- **Label every unconfirmed figure as an estimate.** Prices, opening hours, weather, venue existence.
- **Markdown output only** — never PDF.
- **Guards fail loudly.** If a check can't determine its answer, it must error, never silently pass.
- **`uv` is the only supported toolchain.** `uv sync` / `uv run`; don't add `pip`/`requirements.txt` paths back.
- **`CLAUDE.md` is the authority on behavior; this file on structure.** Keep them consistent.
