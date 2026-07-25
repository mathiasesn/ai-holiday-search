---
name: trip-scraper
description: Search orchestration across flight, stay, and package sources for /scrape. Fans out to the .agents/skills adapters, normalizes results into a common candidate record, deduplicates against trip_scraper/seen.json, and falls back to Claude web search or a paste-a-listing flow when an adapter has no credentials or a site can't be queried directly.
---

# Trip Scraper

Search orchestration used by `/scrape`. It does not itself hold search logic for any one
source — it fans out to the thin adapters in `.agents/skills/`, normalizes what they return,
deduplicates against previously seen candidates, and hands the result set to `holiday-planner`'s
fit-scoring framework (`03-trip-evaluation.md`) for ranking.

## Default search settings

Destinations, date windows, price ceiling, and sources queried by default live in
[search-queries.md](search-queries.md) — a tracked generic template, filled in per-traveler by
`/setup` at `profile/search-queries.md` (which wins if present).

## Fan-out to source adapters

For each configured source, run the adapter's CLI:

```
python .agents/skills/flights-search/search.py --json <args>
python .agents/skills/stays-search/search.py --json <args>
python .agents/skills/packages-search/search.py --json <args>
```

- Each adapter is stdlib+`requests`, supports `--help`, and exits non-zero on failure.
- **Missing credentials:** an adapter that needs an API key it doesn't have (e.g. no
  `AMADEUS_API_KEY`) exits with a distinct non-zero "no credentials" status and a message on
  stderr. On that exit, do **not** treat it as a hard failure — fall back to Claude's own web
  search for that source, using the same query parameters, and normalize the results the same
  way.
- Any other non-zero exit is a real failure: report it, skip that source for this run, continue
  with the others.

## Paste-a-listing fallback

When a source can't be queried at all (bot-blocked, no adapter, or the user already found a
specific deal), the user may paste a listing, package page, or email text directly into chat.
Parse it into the same normalized candidate record below with `"source": "pasted"` and run it
through the same dedup + scoring pipeline as any other candidate.

## Normalized candidate record

Every result, regardless of source, is normalized to this shape before scoring:

```json
{
  "source": "flights-search",
  "destination": "Porto, Portugal",
  "origin": "CPH",
  "depart_date": "2026-10-14",
  "return_date": "2026-10-19",
  "nights": 5,
  "price": 732,
  "currency": "EUR",
  "per_person": true,
  "trip_type": "flight+stay",
  "url": "https://example.com/listing/12345",
  "raw_notes": "direct flight, 3-star apartment, breakfast not included",
  "retrieved_at": "2026-07-25T10:32:00+02:00"
}
```

`price`/`currency`/`per_person` follow the currency handling rules in
`.claude/skills/holiday-planner/05-budget-rules.md`. `url` is omitted (or `null`) for pasted listings without a
link.

## Deduplication against trip_scraper/seen.json

Before presenting results, drop any normalized candidate whose dedupe key already exists in
`trip_scraper/seen.json` **and** whose price hasn't moved into a new bucket (see format below) —
otherwise it's a legitimate price-change re-surface, not a duplicate. New or price-changed
candidates get written/updated back into `seen.json` after presenting them.

### Dedupe key derivation

```
dedupe_key = sha256(f"{source}|{destination_slug}|{depart_date}|{return_date}|{price_bucket}")
```

- `destination_slug`: lowercase, ASCII, spaces→hyphens (e.g. `porto-portugal`).
- `price_bucket`: price rounded down to the nearest 50 currency units, so small fare
  fluctuations don't create false-new entries (e.g. €732 → bucket `700`).

### `trip_scraper/seen.json` format

```json
{
  "schema_version": 1,
  "entries": {
    "3f1a9c2b7e4d5f6a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a": {
      "source": "flights-search",
      "destination": "Porto, Portugal",
      "depart_date": "2026-10-14",
      "return_date": "2026-10-19",
      "price_bucket": 700,
      "currency": "EUR",
      "first_seen": "2026-07-25T10:32:00+02:00",
      "last_seen": "2026-07-25T10:32:00+02:00"
    }
  }
}
```

- `entries` is keyed by the dedupe key above.
- `first_seen` is set once, on first sighting; `last_seen` is updated to the current run's
  timestamp every time the same key is seen again. Both are ISO-8601 with timezone offset.
- If `trip_scraper/seen.json` doesn't exist yet, create it with `schema_version: 1` and an
  empty `entries` object, then populate it.

## Handing off to scoring

Once deduplicated, pass the normalized candidate list to the fit-scoring framework in
`.claude/skills/holiday-planner/03-trip-evaluation.md`, sorted by score descending, each with its reasoning
shown per the format in that file.
