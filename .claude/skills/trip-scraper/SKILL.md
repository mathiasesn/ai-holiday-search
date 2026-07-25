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

Stays are queried through every enabled stays source. Today that is the `stays-search` CLI
adapter below, plus `trivago-search` and `momondo-search`, browser-driven skills (not CLI
adapters — see next section). Flights and packages are queried through their CLI adapters plus
`momondo-search`, which covers all three verticals.

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

### Browser-driven sources (not exit-code adapters)

A source may instead be browser-driven rather than a CLI adapter: it has no `search.py`,
no CLI invocation, and no exit code — it drives a real browser session, defines its own
fallback chain instead of the exit-2 no-credentials protocol above, and normalizes its results
into the same adapter result record. `trivago-search` is one instance, stays-only: it runs on
every `/scrape`, alongside (not instead of) `stays-search`, driving a session per
`.claude/skills/trivago-search/SKILL.md` (whose default driver is the `claude-in-chrome` MCP
tools) — that file is authoritative for its exact fallback trigger list and order, do not
re-enumerate it here.

`momondo-search` is the other current instance, and unlike `trivago-search` it spans **all
three** verticals — flights, stays, and packages — as three parallel procedures inside one
skill. It runs on every `/scrape`, alongside the CLI adapters, for whichever verticals the run
calls for (see the query-driven vertical-selection rule below). It has its own fallback chain,
authoritative in `.claude/skills/momondo-search/SKILL.md`; do not re-enumerate it here. Its
results normalize into the same adapter result record with `source: "momondo-search"`, reading
DKK — the same EUR conversion-estimate rule that applies to `trivago-search` (see
"Normalization" in that skill and `.claude/skills/holiday-planner/05-budget-rules.md`) applies
here too.

**Vertical selection is query-driven, not always-on.** `/scrape` runs only the `momondo-search`
verticals the traveler's request and profile actually call for — a flight-only query runs
flights alone; a "week in Lisbon, flights and hotel" query runs flights, stays, and packages.
Name which verticals ran in the final output, and say plainly when one was skipped rather than
letting it pass silently. When the request is ambiguous about which verticals are wanted, ask
the user rather than silently running all three.

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

## Cross-source duplicate presentation (presentation and ranking only)

This is separate from `seen.json` dedupe above (which is unchanged) — it happens at
presentation time, after scoring: whenever the same underlying property or itinerary is
surfaced by more than one enabled source, at a different price, **both rows are shown
separately** — each with its own price and `source` — visibly grouped or marked as the same
underlying property, with the price gap noted as further evidence both figures are estimates.
This supersedes any earlier "collapse into one row" behavior; do not merge the rows away.

Critically, the linked rows are **one candidate presented with two quotes, not two
candidates**: it is scored and ranked **once**, using the **lower** of the two prices. A future
third source inherits this rule automatically; it is not specific to any one pair of sources.

Example: `trivago-search` and `momondo-search` both read DKK, `stays-search` is typically EUR —
**convert to a common currency before comparing "lower"; never compare raw numbers in different
currencies** (a DKK figure looks smaller than an EUR one at the same real price and would
silently win every time; see `.claude/skills/holiday-planner/05-budget-rules.md` for the
conversion/labeling policy). Name both sources on their respective rows — format example only,
not a real or current price: "trivago-search: kr 8,778" shown grouped with "momondo-search: kr
9,150 — same property, price gap likely fees/timing; both are estimates", scored once at the
lower (trivago) figure. Any currency conversion is itself an estimate (rate not pinned), on top
of each source's existing web-read-estimate label.

## Handing off to scoring

Once deduplicated, pass the normalized candidate list to the fit-scoring framework in
`.claude/skills/holiday-planner/03-trip-evaluation.md`, sorted by score descending, each with its reasoning
shown per the format in that file.
