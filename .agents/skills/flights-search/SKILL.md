---
name: flights-search
description: Search flight offers via the Amadeus Self-Service API (free tier), with a documented no-credentials fallback to Claude web search.
---

# flights-search

## What this covers

Round-trip or one-way flight offer search between two airports on given dates, via the
[Amadeus Self-Service](https://developers.amadeus.com/self-service) `flight-offers` API
(test/sandbox environment). Covers most major European and international routes at
free-tier rate limits — good enough for exploratory search, not for booking-grade
availability.

## Setup / credentials

1. Create a free Amadeus for Developers account and a Self-Service app:
   https://developers.amadeus.com/register
2. Set two environment variables locally (never commit these):
   - `AMADEUS_API_KEY`
   - `AMADEUS_API_SECRET`
3. (Optional) Set `AMADEUS_HOSTNAME` to select which Amadeus API host to call:
   - `test` (default if unset) — the test/sandbox host, `test.api.amadeus.com`.
   - `production` — the production host, `api.amadeus.com` (requires production
     credentials, not test/sandbox ones).
   - Any other value is used verbatim as a full hostname (e.g. a self-hosted proxy).
   - Using test-environment credentials against `production` (or vice versa) is a
     common cause of `401` errors — check `AMADEUS_HOSTNAME` matches your credential type.
4. No credentials needed to run `--help`, and no crash occurs if they're unset —
   see Fallback behavior below.

## CLI invocation

```
uv run .agents/skills/flights-search/search.py \
  --origin CPH --destination BCN \
  --depart 2026-10-12 --return-date 2026-10-19 \
  --adults 2 --currency EUR --max-results 10 --json
```

Flags: `--origin`, `--destination` (IATA codes), `--depart` (YYYY-MM-DD),
`--return-date` (optional, omit for one-way), `--adults` (default 1), `--currency`
(default `EUR`), `--max-results` (default 10), `--json` (emit a JSON array instead of
plain text).

## Result shape

Each result has `source`, `title`, `url`, `price`, `currency`, `price_per_person`,
`dates` (`{depart, return}`), and free-form `details` (here: raw Amadeus itinerary
segments). See [../../../skills/trip-scraper/SKILL.md](../../../skills/trip-scraper/SKILL.md) ("Adapter result record") for
the authoritative field-by-field definition, shared across all three
`.agents/skills/*` adapters. `--json` with no matches prints `[]`.

## Fallback behavior

If `AMADEUS_API_KEY` or `AMADEUS_API_SECRET` is unset, the CLI does **not** attempt a
network call. It prints a machine-readable status and exits **2**:

```json
{"status": "no_credentials", "reason": "missing_api_credentials", "message": "...", "fallback": "web_search", "results": []}
```

This is the adapter no-credentials protocol — see [../../../skills/trip-scraper/SKILL.md](../../../skills/trip-scraper/SKILL.md) for the
authoritative shape shared by all three adapters. Callers (e.g. `/scrape`) should treat exit code
`2` as "use Claude web search for
flights on this route instead of failing the run." Exit code `1` means a genuine
failure (bad arguments, network/HTTP error) and should be reported, not silently
swallowed. Exit code `0` means success (including a valid empty result set).

The API key/secret are never printed, logged, or included in error output.
