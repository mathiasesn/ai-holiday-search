---
name: stays-search
description: Search accommodation via a configured public stays API/feed, with a documented web-search + paste-a-listing fallback when none is configured.
---

# stays-search

## What this covers

Hotel/rental accommodation search for a destination and date range. Unlike
`flights-search`, this adapter does not ship with a bundled commercial API — most
hotel/rental search APIs (Booking.com, Airbnb, Expedia, etc.) require partnership
agreements that aren't appropriate for a public template. Instead it's built around
a pluggable public API/feed (e.g. a national tourism board open-data feed, or any
JSON API you have access to) with Claude web search + paste-a-listing as the default,
always-available path.

## Setup / credentials

Optional. To enable the API path, set:

- `STAYS_API_URL` — base URL of a JSON stays API/feed that accepts `destination`,
  `check_in`, `check_out`, `guests`, `currency`, `limit` query parameters and returns
  either `{"results": [...]}` or a bare JSON array of stay objects.
- `STAYS_API_KEY` — optional, sent as `Authorization: Bearer <key>` if your source
  requires auth.

If `STAYS_API_URL` is unset (the default, out of the box), the CLI never makes a
network call — see Fallback behavior below.

## CLI invocation

```
python .agents/skills/stays-search/search.py \
  --destination Lisbon \
  --check-in 2026-10-12 --check-out 2026-10-19 \
  --guests 2 --currency EUR --max-results 10 --json
```

Flags: `--destination`, `--check-in` / `--check-out` (YYYY-MM-DD), `--guests`
(default 2), `--currency` (default `EUR`), `--max-results` (default 10), `--json`
(emit a JSON array instead of plain text).

## Result shape

Each result has `source`, `title`, `url`, `price`, `currency`, `price_per_person`,
`dates` (`{check_in, check_out}`), and free-form `details` (whatever extra fields the
configured source returns). See `.claude/skills/trip-scraper/SKILL.md` ("Adapter
result record") for the authoritative field-by-field definition, shared across all
three `.agents/skills/*` adapters. `--json` with no matches prints `[]`.

## Fallback behavior

If `STAYS_API_URL` is unset, the CLI does not attempt a network call. It prints a
machine-readable status and exits **2**:

```json
{"status": "no_credentials", "reason": "no_source_configured", "message": "...", "fallback": "web_search", "results": []}
```

This is the adapter no-credentials protocol — see `.claude/skills/trip-scraper/SKILL.md` for the
authoritative shape shared by all three adapters. Callers (e.g. `/scrape`) should treat exit code
`2` as "use Claude web search for
stays in this destination instead of failing the run," and use the paste-a-listing
path in `/plan` for any specific listing the user finds manually. Exit code `1` means
a genuine failure (bad arguments, network/HTTP error against a configured source) and
should be reported. Exit code `0` means success (including a valid empty result set).

`STAYS_API_KEY`, if set, is never printed, logged, or included in error output.
