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
3. No credentials needed to run `--help`, and no crash occurs if they're unset —
   see Fallback behavior below.

## CLI invocation

```
python .agents/skills/flights-search/search.py \
  --origin CPH --destination BCN \
  --depart 2026-10-12 --return-date 2026-10-19 \
  --adults 2 --currency EUR --max-results 10 --json
```

Flags: `--origin`, `--destination` (IATA codes), `--depart` (YYYY-MM-DD),
`--return-date` (optional, omit for one-way), `--adults` (default 1), `--currency`
(default `EUR`), `--max-results` (default 10), `--json` (emit a JSON array instead of
plain text).

## Result shape

Every result is a normalized record, shared across all three `.agents/skills/*`
adapters:

```json
{
  "source": "flights-search",
  "title": "Flight offer 1",
  "url": null,
  "price": 412.30,
  "currency": "EUR",
  "price_per_person": 206.15,
  "dates": {"depart": "2026-10-12", "return": "2026-10-19"},
  "details": {"id": "1", "numberOfBookableSeats": 4, "itineraries": [...]}
}
```

`--json` with no matches prints `[]`. `details` is free-form and carries the raw
Amadeus itinerary segments for anyone who wants flight-number-level detail.

## Fallback behavior

If `AMADEUS_API_KEY` or `AMADEUS_API_SECRET` is unset, the CLI does **not** attempt a
network call. It prints a machine-readable status and exits **2**:

```json
{"status": "no_credentials", "message": "...", "fallback": "web_search", "results": []}
```

Callers (e.g. `/scrape`) should treat exit code `2` as "use Claude web search for
flights on this route instead of failing the run." Exit code `1` means a genuine
failure (bad arguments, network/HTTP error) and should be reported, not silently
swallowed. Exit code `0` means success (including a valid empty result set).

The API key/secret are never printed, logged, or included in error output.
