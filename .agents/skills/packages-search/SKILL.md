---
name: packages-search
description: Working template adapter for package/charter holiday operators — fork and edit to point at a local operator's API.
---

# packages-search

## What this covers

Package/charter holiday search (flight + hotel bundles), the kind sold by national
charter operators. This skill ships as a **working template, not a live
integration** — no operator is bundled, since these are typically regional and
require a commercial API agreement. It runs cleanly out of the box and reports that
no operator is configured. PRs adding country-specific forks of this skill are
welcome (see the README's Search sources section).

## Setup / credentials

Optional, and off by default. To wire up a real operator:

1. Set `PACKAGES_API_URL` (required to enable this skill) and `PACKAGES_API_KEY`
   (optional, sent as `Authorization: Bearer <key>` if required).
2. Edit `fetch_packages()` in `search.py` to call your operator's actual endpoint
   (method, auth scheme, params) — the shipped version is a generic GET placeholder.
3. Edit `parse_results(payload) -> list[dict]` in `search.py` — **this is the seam**.
   It receives your operator's JSON-decoded response and must return a list of dicts
   with at least `name`/`title`, `price`, `currency`, `url`, and dates; everything
   else is preserved as free-form detail. Nothing else in the file needs to change.
4. Update this file to describe your operator, its coverage, and credentials.

## CLI invocation

```
python .agents/skills/packages-search/search.py \
  --destination Antalya --depart-airport CPH \
  --depart 2026-10-12 --return-date 2026-10-19 \
  --adults 2 --currency EUR --max-results 10 --json
```

Flags: `--destination`, `--depart-airport` (home airport IATA code), `--depart`
(YYYY-MM-DD), `--return-date` (optional), `--adults` (default 2), `--currency`
(default `EUR`), `--max-results` (default 10), `--json` (emit a JSON array instead of
plain text).

## Result shape

Every result is a normalized record, shared across all three `.agents/skills/*`
adapters:

```json
{
  "source": "packages-search",
  "title": "7 nights all-inclusive, Antalya",
  "url": "https://example-operator.com/package/456",
  "price": 1980.0,
  "currency": "EUR",
  "price_per_person": 990.0,
  "dates": {"depart": "2026-10-12", "return": "2026-10-19"},
  "details": {"hotel": "Example Resort & Spa", "board": "all-inclusive"}
}
```

`--json` with no matches, or with no operator configured, prints `[]` /
`{"results": []}` respectively. `details` carries whatever your `parse_results()`
fork leaves on each item beyond the normalized core fields.

## Fallback behavior

If `PACKAGES_API_URL` is unset (the out-of-the-box default), the CLI does not attempt
a network call. It prints a machine-readable status and exits **2**:

```json
{"status": "no_operator_configured", "message": "...", "fallback": "web_search", "results": []}
```

Callers (e.g. `/scrape`) should treat exit code `2` as "no local operator configured
— use Claude web search + paste-a-listing for package holidays instead of failing the
run." Exit code `1` means a genuine failure (bad arguments, network/HTTP error against
a configured operator, or an operator payload `parse_results()` couldn't handle) and
should be reported. Exit code `0` means success (including a valid empty result set).

`PACKAGES_API_KEY`, if set, is never printed, logged, or included in error output.
