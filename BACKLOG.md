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

### 6. Pin `requirements.txt`, enable Dependabot

`requests` is currently unpinned, so CI and a fresh fork can resolve different
versions — a green CI run does not prove a forker's install works. Pin, then
let Dependabot propose upgrades.

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

## Features

Consolidated here from the README Roadmap; this file is the single list.

- [ ] `/pack` — profile-aware packing list generation per trip
- [ ] Multi-destination trips (open-jaw flights, rail legs)
- [ ] Calendar export (.ics) of final itineraries
- [ ] Community skills for national charter operators
- [ ] PDF/LaTeX itinerary compilation (Markdown output is the default; PDF is
      optional future tooling)
