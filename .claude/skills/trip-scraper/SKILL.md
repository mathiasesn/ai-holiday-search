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

## Fan-out to sources

Stays are queried through two sources, not one: the `stays-search` CLI adapter below, and
`trivago-search`, a browser-driven skill (not a CLI adapter — see next section). Flights and
packages only have the CLI adapters.

For each configured CLI-adapter source, run the adapter's CLI:

```
uv run .agents/skills/flights-search/search.py --json <args>
uv run .agents/skills/stays-search/search.py --json <args>
uv run .agents/skills/packages-search/search.py --json <args>
```

- Each adapter is stdlib+`requests`, supports `--help`, and exits non-zero on failure.
- **Missing credentials — the adapter protocol (authoritative here):** when an adapter needs
  credentials/config it doesn't have (e.g. no `AMADEUS_API_KEY`), it MUST print exactly one JSON
  object to stdout and exit with code **2**:

  ```json
  {"status": "no_credentials", "reason": "<machine token>", "message": "<human sentence>", "fallback": "web_search", "results": []}
  ```

  - `status` is always the literal `"no_credentials"`.
  - `reason` is a per-adapter machine token distinguishing *why* (e.g.
    `missing_api_credentials`, `no_source_configured`, `no_operator_configured`) — do not match
    on this for control flow, only `status` and the exit code.
  - `message` is a human-readable sentence for display.
  - `fallback` is always `"web_search"`.
  - `results` is always `[]`.

  Any forked or new adapter under `.agents/skills/` MUST emit this exact shape on its
  no-credentials path. On exit code 2 with `status == "no_credentials"`, do **not** treat it as a
  hard failure — fall back to Claude's own web search for that source, using the same query
  parameters, and normalize the results the same way.
- Any other non-zero exit is a real failure: report it, skip that source for this run, continue
  with the others.

### trivago-search: browser-driven, not an exit-code adapter

`trivago-search` is a first-class stays source that runs on every `/scrape`, alongside (not
instead of) `stays-search`. It has no `search.py`, no CLI invocation, and no exit code — it drives
a real browser session per `.claude/skills/trivago-search/SKILL.md`, whose default driver is the
`claude-in-chrome` MCP tools. It is therefore exempt from the exit-2 no-credentials protocol
above; it has its own fallback chain instead — `.claude/skills/trivago-search/SKILL.md` is
authoritative for the exact trigger list and order, do not re-enumerate it here. Every price it
produces is a web-read estimate and must be labeled as such.

## Adapter result record (authoritative)

Each `.agents/skills/*/search.py` adapter's `--json` output is a JSON array of records in this
exact shape (this is the single authority for this record — adapter `SKILL.md` files and module
docstrings only summarize it and point back here):

| Field              | Type            | Notes                                                        |
|---------------------|-----------------|---------------------------------------------------------------|
| `source`            | `str`           | Adapter name, e.g. `"flights-search"`.                        |
| `title`              | `str`           | Human-readable listing title.                                 |
| `url`                | `str \| None`   | Listing URL, or `null` if the source doesn't provide one.      |
| `price`              | `float`         | Total price for the listing.                                  |
| `currency`           | `str`           | ISO currency code, e.g. `"EUR"`.                               |
| `price_per_person`   | `float`         | `price` divided by the relevant traveler count.                |
| `dates`              | `dict`          | `{"depart", "return"}` for flights/packages, `{"check_in", "check_out"}` for stays. |
| `details`            | `dict`          | Free-form, source-specific extra fields.                       |

`--json` with no matches prints `[]`. This record is distinct from the post-fan-out "Normalized
candidate record" below, which `trip-scraper` produces by merging one or more of these adapter
records with destination/trip context for scoring.

`trivago-search` results normalize into this same record shape, with `source: "trivago-search"`,
even though they come from a browser read rather than a `--json` CLI call.

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

## Cross-source duplicate collapsing (presentation only)

Because `trivago-search` is metasearch, it routinely surfaces the same property that
`stays-search` also found, at a different price. This is separate from `seen.json` dedupe above
(which is unchanged) — it happens at presentation time, after scoring: when the same property
appears from both sources, collapse them into a single presented candidate showing the lower
price and naming both sources. `trivago-search` reads DKK, `stays-search` is typically EUR —
**convert both to a common currency before comparing "lower"; never compare raw numbers in
different currencies** (a DKK figure looks smaller than an EUR one at the same real price, ~7.5
kr per euro, and would silently win every time). Name the other source in the collapsed entry —
format example only, not a real or current price: "also on stays-search at €812". Every
`trivago-search` price involved is a
web-read estimate, and any currency conversion is itself an estimate (rate not pinned).

## Handing off to scoring

Once deduplicated, pass the normalized candidate list to the fit-scoring framework in
`.claude/skills/holiday-planner/03-trip-evaluation.md`, sorted by score descending, each with its reasoning
shown per the format in that file.
