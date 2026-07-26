# Backlog

Known work not yet done, in rough priority order. Engineering debt first, then
planned features. Items here are decisions and debt — not bugs; anything actually
broken should be fixed rather than listed.

## Engineering

### 1. Tests for `tools/lint_skills.py` and `tools/security_guards.py`

CI asserts only that both scripts exit 0. That cannot distinguish a working
guard from a guard that checks nothing — two real instances of exactly that
shipped and were caught only by manual probing:

- `git check-ignore` reports nothing for tracked paths (tracking beats
  `.gitignore`), so the personal-data leak check passed unconditionally until
  `--no-index` was added.
- `git check-ignore -v` reports the last matching pattern *including
  negations*, so every deliberately-tracked `.gitkeep` and `documents/README.md`
  was misreported as a leak.

Needed: fixture-based tests asserting the guards **fail** on planted leaks — a
force-added `profile/*.md`, a tracked `.env`, a real-looking secret in all four
quoting styles — and pass on the clean tree. Assert exit codes in both
directions.

### 2. Security guards as a pre-commit hook

The guards run in CI, which means a leaked traveler profile is caught only
after it reaches the remote — for personal travel data, that is already too
late. Install `tools/security_guards.py` as a `pre-commit` hook so the check
fires where it matters. Keep the CI job as the backstop for anyone who commits
with `--no-verify`.

### 3. Round-trip test for state-file schemas

`trip_scraper/seen.json` and `watchlist/<slug>.json` are defined in the skills
and consumed by the commands, but the agreement between them is enforced only
by prose. A command file can drift from its skill's schema with nothing
failing. Needed: a fixture-driven test that writes and re-reads each state file
against the documented shape (dedupe key derivation, `first_seen`/`last_seen`
semantics, price-history append).

### 4. Decide the `.claude/settings.local.json` question

The README file tree lists `.claude/settings.local.json`, but that path is
matched by a common global gitignore (`~/.config/git/ignore`), so a fresh clone
never receives it — the tree documents a file that cannot exist for some users.
Pick one: force-add it, or change the tree to reference a shareable
`.claude/settings.json` and leave `.local.json` as untracked per-user state.
The second is likely correct, since the file holds personal permission grants.

### 5. ~~Decide whether `specs/` stays tracked~~ — resolved

Resolved: specs are local working state, not framework content. `specs/` has
its own `.gitignore` containing `*`, and the one tracked spec was untracked
with `git rm --cached` (the file stays on disk). `specs/` is deliberately
absent from the README file tree.

Kept here as a record because the contradiction — a gitignored directory with a
tracked file inside it — is what `tools/security_guards.py` flagged, and is the
kind of drift the guard exists to catch.

### 6. Pin dependencies — resolved for tooling; adapters still unpinned

Resolved for the project environment: `tools/` and the project itself moved
from `requirements.txt` to uv, with dependencies declared in `pyproject.toml`
and pinned via a committed `uv.lock` — a green CI run now proves a forker's
`uv sync` resolves the same versions.

Still open: the three adapters are invoked as `uv run <path>/search.py` and
carry PEP 723 inline metadata (`dependencies = ["requests"]`). `uv run` on a
script resolves an isolated environment from that inline block — it does not
consult `pyproject.toml` or `uv.lock` — so `requests` still resolves unpinned
on each adapter run. `uv lock --script <file>` would produce a per-script
lockfile for this but has not been adopted. Also still open: enable Dependabot
(or an equivalent) to propose upgrades against `uv.lock` — note it would cover
only the lockfile, not the adapters' inline headers. See also item 8: nothing
currently verifies those headers at all.

Also now open: `.mcp.json` pins the Playwright MCP server as
`@playwright/mcp@0.0.78`, but via `npx -y`, which resolves from the npm
registry at run time rather than a committed lockfile — a third pinning
mechanism in this repo, alongside `uv.lock` and the adapters' PEP 723 headers,
and not covered by the `uv sync`/Dependabot coverage described above.

### 7. Shared adapter code (`.agents/skills/_common.py`)

The three `search.py` adapters share roughly 330 near-identical lines
(argument parsing, the no-credentials payload, error handling).

**This was considered and deliberately rejected**, and should not be
"fixed" without revisiting the constraint: `search.py` is invoked as a bare
path with no package setup, so a copied skill folder would be import-broken and
the documented copy-a-folder fork workflow would break. The duplication is
currently guarded by a CI check that executes each adapter with credentials
unset and fails on any drift in the contract. Reopen only if the fork workflow
changes — and if you do, the CI drift check is the thing to preserve.

The drift check lives in `check_adapter_contract()` in `tools/lint_skills.py`.
Note what it does *not* cover — see item 8.

### 8. Nothing exercises the adapters' PEP 723 dependency block

Each adapter declares `dependencies = ["requests"]` in its inline script
metadata, and that header is what makes the copy-a-folder fork workflow work.
No check currently proves the header is correct:

- `requests` is imported lazily *inside* `main()`, after the no-credentials
  early return. So neither `--help` (the `adapter-smoke` and
  `standalone-adapter` jobs) nor `--json` (the contract check in item 7) ever
  reaches the import.
- An adapter whose header listed no dependencies, or misspelled `requests`,
  would pass every check green and fail only for a forker at first real search.
- `uv sync --script <file>` is not a fix — it exits 0 on an emptied
  `dependencies` list (verified).

This is also the reason the duplication in item 6 — `requests` declared in both
`pyproject.toml` and three headers — is currently *undetectable* rather than
merely un-automated.

Options, cheapest first: run one adapter past the credential gate with dummy
credentials and assert stderr does not contain the "requests package is
required" message (costs a network call, so mildly flaky); or add a lint rule
comparing each header's dependency list against `pyproject.toml`. The lint rule
was offered during planning and declined as over-engineering — reopen it only if
a second dependency ever appears, at which point the drift risk stops being
theoretical.

### 9. `tools/` is never executed on the declared 3.10 floor

`pyproject.toml` sets `requires-python = ">=3.10"` and `adapter-smoke` matrixes
3.10 and 3.12, but `lint-and-guards` runs only on the `.python-version` pin
(3.12). A 3.10-incompatible construct in `tools/lint_skills.py` or
`tools/security_guards.py` ships green and breaks only for a forker on 3.10.
Fix: matrix the `lint-and-guards` job too, or drop the floor to what is actually
tested. Cheap either way; worth doing alongside item 1's fixture tests.

### 10. ~~`/watch` has no path for browser-driven sources~~ — resolved

The browser-driven sources produce candidates with their own `source` values,
but `/watch` and `.claude/skills/price-watch/SKILL.md` know only two kinds of
trip: one re-searchable through a `.agents/skills/*` adapter, and one that was
pasted. A browser-driven candidate matches neither, so `/watch add` on a
`/scrape` result can save a trip that no re-check branch knows how to price
again.

Each source added since had widened this gap. It was a stays-only problem while
`trivago-search` was the sole browser-driven source — a user could at least
re-check flights and packages through the adapters. `momondo-search` covers all
three verticals and `booking-search` covers stays and flights, so the
untrackable set had grown to include flight and package candidates too, which
are exactly the ones whose prices move most.

There was a second, harder half. `price-watch` is built for unattended re-checks
and the README said `/watch` can be scheduled via cron or CI — but the
`claude-in-chrome` driver needs an attended session with site permission, so it
cannot run on a schedule at all. The two statements contradicted each other.

Resolved by adding a second driver, Playwright MCP, as an unattended-capable
substitute — this is what closes the contradiction between "`/watch` can run
unattended" and "`claude-in-chrome` needs an attended session." Why: it lets
either driver run all three browser-driven procedures, so scheduling no
longer requires giving up the browser-driven sources. The current
default-per-caller mapping and full capability model are authoritative in
`.claude/skills/trivago-search/SKILL.md` ("Driver model") — do not re-narrate
them here; that file is the one to check if defaults or capabilities ever
change.

Considered and not chosen:

- Degrade browser-driven trips to Claude web search on re-check, and say plainly
  in the report that the price came from a weaker source than the original
  snapshot.
- Refuse `/watch add` for browser-driven candidates and say why.

**Walkthrough performed 2026-07-26.** `/setup` → `/scrape` (claude-in-chrome)
→ `/watch add` → `/watch` (Playwright) ran end to end against real sites. The
dispatch worked: a `trivago-search` candidate was saved and reached the
browser-driven branch, which navigated to the stored `trip.url` — the gap this
item describes is closed and evidenced.

The re-check itself was blocked, and diagnosing it produced the finding worth
keeping. trivago's edge returned `403 Access Denied` on the document at 114 ms,
before any page JavaScript ran, so it was a WAF rejection on request
fingerprint rather than a solvable challenge. The trigger was isolated to a
single token: two `curl` requests to the same URL differing **only** by
`HeadlessChrome/149` vs `Chrome/149` in the User-Agent returned 403 and 200
respectively (200 = 95 KB of real results, no challenge markers). Headless
Chrome advertises `HeadlessChrome` by default, which is what trivago rejects.

Fixed by passing `--user-agent` with an ordinary Chrome UA to the headless
server in `.mcp.json`. Scoped: of the three browser-driven sources, only
trivago blocks the headless UA — momondo returned 200 and booking 202 under
both UAs, so this was never a general "unattended browsing is blocked" problem.

Still open:

- The `--user-agent` fix is verified at the HTTP layer only (`curl`, both UAs,
  all three sources). It has not been re-run through `/watch` itself, which
  needs an MCP reload to pick up the changed `.mcp.json`.
- The UA pins a Chrome major version in a tracked file and will drift from
  whatever Chromium `@playwright/mcp` ships. It only has to avoid saying
  `Headless`, so drift degrades slowly rather than breaking — but it is one
  more pinned string, related to item 6.
- `playwright-headed` is declared in `.mcp.json` but did not connect during the
  walkthrough, so the attended-debugging path remains unexercised.
- momondo and booking have still never been read through Playwright; only
  trivago has, and only as far as the 403.

### 11. Nothing verifies a browser-driven source

CI cannot exercise any browser-driven source: there is no browser in the runner,
and every one of these procedures depends on a live third-party site.
`tools/lint_skills.py` checks frontmatter and links, which proves the files are
well-formed and proves nothing about whether the procedures still work.

The specific decay risks, all recorded in the skills themselves:

- **trivago:** the `search=` URL grammar was captured from one live session;
  `drs-40` has an unknown meaning and the Danish locale segment was never
  confirmed. `locationId` values are opaque and site-assigned, so a stale one
  silently returns the wrong city rather than failing. Card layout drives the
  per-night-vs-total price distinction.
- **momondo:** three verticals means roughly triple the surface. The flights URL
  grammar is derivable, but stays has none (the form is the only path, and its
  `-p<id>` place ID and `ucs=` token are opaque), and two segments of the
  packages URL are marked unverified. Each vertical has its own price trap, and
  flights and packages are *inverted* — the headline is per-person on one and
  the total on the other, so a DOM change that swaps them produces plausible
  wrong numbers. The stays price basis depends on a `Pris:` dropdown that
  defaults to per-night.
- **booking:** the same per-person-vs-total inversion across its two verticals —
  the stays headline is the stay total including taxes, the flights headline is
  per person with the party total on a smaller line beneath. The flights read
  spans a second domain (`flights.booking.com`, operated by a third party), so
  it can rot independently of the stays flow. Eight tokens and behaviors are
  marked UNVERIFIED in the skill and must not be silently promoted to fact on a
  later pass. The absence of a packages vertical is a **negative** finding
  verified on one date — if booking.com ever ships a bundled product, nothing
  will notice.

Every one of these is a silent-wrong-number risk, not a crash: the failure mode
is a shortlist that looks fine and is priced wrong.

Widened by item 10's resolution: the verification surface now spans **two
drivers**, `claude-in-chrome` and Playwright MCP. Both read the same card
layouts and price-basis rules, but nothing proves they stay in agreement — the
same skill can produce different numbers depending on which driver ran it,
which stacks a new silent-wrong-price risk on top of the ones above.

This is not fixable by a normal test, and mocking the sites would only assert
that the mock matches the doc. The realistic options are a manual
re-verification checklist run when results look wrong, or an opt-in live smoke
check that is never part of required CI. Related to item 1: exit 0 is not
evidence.

Each skill records the date its facts were captured (all three 2026-07-25) —
that date is the closest thing to a freshness signal this repo has, and a
re-verification pass should update it.

### 12. Two accepted-for-now design debts from the browser-driven /watch work

Not bugs — deliberate calls, recorded so they aren't rediscovered as if new.

**Trip-kind dispatch is enumerated in three places.** `price-watch/SKILL.md`,
`.claude/commands/watch.md`, and `trip-scraper/SKILL.md` each spell out the
six source names when dispatching on trip/candidate kind. A fourth
browser-driven source means editing all three. The deeper fix is a
`kind: adapter | browser | pasted` property declared per source skill and
carried in the candidate record next to `source`, so dispatch reads the
property instead of naming sources. This is consistent with the shape
`trip-scraper` already uses ("Today that is…" kind reasoning), so the current
enumeration is acceptable now and worth replacing when a fourth
browser-driven source appears.

**`profile/tooling.md` puts runtime tool selection inside a gitignored
traveler-preference directory.** That's why the "absence means the caller
default" rule needs restating defensively in `/scrape`, `/watch`, and the
skills they call. `.mcp.json` / `.claude/settings.json` is arguably the more
natural home for a tooling knob like this. Keeping it under `profile/` was a
deliberate choice — it keeps the knob out of the six travel-preference files
and out of anything that could be mistaken for shared framework config — and
its cost is documentation drift (the absence rule stated in more than one
place), not breakage.

## Features

Consolidated here from the README Roadmap; this file is the single list.

- [ ] `/pack` — profile-aware packing list generation per trip
- [ ] Multi-destination trips (open-jaw flights, rail legs)
- [ ] Calendar export (.ics) of final itineraries
- [ ] Community skills for national charter operators
- [ ] PDF/LaTeX itinerary compilation (Markdown output is the default; PDF is
      optional future tooling)
