---
name: price-watch
description: Snapshot and re-check logic for /watch. Saves a trip's price snapshot to watchlist/<slug>.json when added, and on each re-check re-searches the same route/dates via trip-scraper's adapters to compare against price history and report drops, rises, and sold-out warnings.
---

# Price Watch

Snapshot and re-check logic used by `/watch`. A watched trip is a saved reference to a
specific route/dates/source, with a price history that grows every time `/watch` re-checks it.

## Slug derivation

Each watched trip gets a stable, filesystem-safe slug used as its filename and as its identity
across `/watch add`, `/watch`, and `/watch remove`:

```
slug = f"{destination_ascii_lowercase_hyphenated}-{depart_date}-{return_date}"
```

Example: "Porto, Portugal", 2026-10-14 → 2026-10-19 → `porto-portugal-2026-10-14-2026-10-19`.
If the same destination/dates are watched from two different sources, append a short source tag:
`porto-portugal-2026-10-14-2026-10-19-flights-search`.

## `watchlist/<slug>.json` format

```json
{
  "schema_version": 1,
  "slug": "porto-portugal-2026-10-14-2026-10-19",
  "trip": {
    "source": "flights-search",
    "destination": "Porto, Portugal",
    "origin": "CPH",
    "depart_date": "2026-10-14",
    "return_date": "2026-10-19",
    "url": "https://example.com/listing/12345"
  },
  "original_snapshot": {
    "price": 732,
    "currency": "EUR",
    "captured_at": "2026-07-25T10:32:00+02:00"
  },
  "price_history": [
    {
      "checked_at": "2026-07-25T10:32:00+02:00",
      "price": 732,
      "currency": "EUR",
      "available": true
    },
    {
      "checked_at": "2026-08-01T09:15:00+02:00",
      "price": 689,
      "currency": "EUR",
      "available": true
    }
  ]
}
```

- `original_snapshot` is written once, when `/watch add` first saves the trip, and never
  changed afterward — it's the baseline every later check compares against.
- `price_history` gets a new entry appended on every `/watch` re-check (including the very
  first one, which duplicates `original_snapshot`). Never overwrite or drop earlier entries.
- `trip` mirrors the normalized candidate record fields from `.claude/skills/trip-scraper/SKILL.md` needed to
  re-run the same search: source, route, dates, url.

## Adding a trip (`/watch add`)

1. Take the trip from the most recent `/scrape` or `/plan` output (or a pasted listing).
2. Derive the slug.
3. Write `watchlist/<slug>.json` with `original_snapshot` and a first `price_history` entry
   equal to it.

## Re-check procedure (`/watch`)

For every file in `watchlist/`:

1. Re-run the same source adapter (or the pasted-listing paraphrase, if `source: "pasted"` and
   no live re-query is possible — in that case, ask the user to re-paste, or skip with a note).
   Use `trip-scraper`'s fan-out and fallback rules (adapter → web search on missing credentials).
2. Compare the new price/availability against the **most recent** `price_history` entry (not
   just the original snapshot).
3. Append a new `price_history` entry with `checked_at` set to now (ISO-8601, with offset).
4. Report per the thresholds below.

## Reporting thresholds

- **Price drop:** new price is **≥5% lower** than the most recent prior entry → report as a
  drop, showing € amount and % change from both the most recent check and the original snapshot.
- **Price rise:** new price is **≥5% higher** than the most recent prior entry → report as a
  rise, same detail.
- **No material change:** difference is within ±5% → note "unchanged" in the summary but still
  record the entry.
- **Sold out / unavailable:** adapter or web search finds no matching listing, or explicitly
  reports unavailability → set `available: false` for that entry and report a **sold-out
  warning**, distinct from a price change. Keep watching (do not auto-remove) unless the user
  runs `/watch remove`.

## Removing a trip (`/watch remove`)

Delete `watchlist/<slug>.json`. Confirm the slug and destination with the user before deleting.
