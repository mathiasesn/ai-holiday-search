---
name: price-watch
description: Snapshot and re-check logic for /watch. Saves a trip's price snapshot to watchlist/<slug>.json when added, and on each re-check re-searches the same route/dates via trip-scraper's adapters or the browser-driven skills to compare against price history and report drops, rises, and sold-out warnings.
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

## `<DATA_ROOT>/watchlist/<slug>.json` format

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
- `trip` mirrors the normalized candidate record fields from `<FRAMEWORK_ROOT>/skills/trip-scraper/SKILL.md` needed to
  re-run the same search: source, route, dates, url.

## Adding a trip (`/watch add`)

1. Take the trip from the most recent `/scrape` or `/plan` output (or a pasted listing).
2. Derive the slug.
3. Write `<DATA_ROOT>/watchlist/<slug>.json` with `original_snapshot` and a first `price_history` entry
   equal to it.

## Re-check procedure (`/watch`)

### Once per run, before the per-trip loop

If any watched trip is browser-driven (`trip.source` one of `"trivago-search"`,
`"momondo-search"`, `"booking-search"`), resolve the driver once (per `/watch`'s own
driver-resolution step) and, if it's available, open **one** browser context and clear its
consent/cookie wall **once** — not per trip. Reuse that same context for every browser-driven
trip in this run; do not re-open a context or re-clear the wall per trip. If the driver is
unavailable per its own readiness check (see the trigger list in
`<FRAMEWORK_ROOT>/skills/trivago-search/SKILL.md` "Fallback chain"), degrade the **whole** browser-driven
branch for this run once, rather than re-discovering the unavailability on every trip.

Apply the same once-per-run economy to a **blocked host**: if a site rejects the document itself
(a 403/429 on navigation, not a consent wall), treat that host as blocked for the rest of the run
and send its remaining trips straight to web search. Re-navigating a host whose edge already
refused the request wastes the navigation and every read after it on each subsequent trip.

### For every file in `<DATA_ROOT>/watchlist/`

1. Dispatch on the trip's kind (identified by `trip.source`):
   - **Adapter-backed** (`source` is one of `flights-search`, `stays-search`,
     `packages-search`): re-run the matching `<FRAMEWORK_ROOT>/.agents/skills/*/search.py --json` adapter for
     the same route/dates, using `trip-scraper`'s fan-out and fallback rules (adapter → web
     search on missing credentials).
   - **Browser-driven** (`source` is one of `"trivago-search"`, `"momondo-search"`,
     `"booking-search"`): using the shared context opened above, **navigate to the stored
     `trip.url` first**; only drive the search form (per that source's documented fast/primary
     path) if `trip.url` no longer resolves to a usable results page. This also removes most of
     the unattended-disambiguation hazard (e.g. trivago's autocomplete), since a stored URL
     needs no destination resolution. The driver contract — tool-capability mapping and
     etiquette limits — lives once in `<FRAMEWORK_ROOT>/skills/trivago-search/SKILL.md`; follow it rather
     than duplicating it here. On any chain-ending condition (bot challenge, consent wall, zero
     results, unreadable page), fall through to Claude web search exactly as the attended
     fallback chain does. If web search also yields nothing, the check is terminal for this trip:
     append a `price_history` entry with `price: null`, `available: null`, and
     `unverified_reason` set to exactly one of `bot_challenge`, `consent_wall`, `unreadable_page`
     — `available: null` means **could not verify**, where `available: false` asserts the trip is
     genuinely gone. Report this distinctly from a genuine sold-out (see thresholds below); a
     blocked read is not evidence a trip is unavailable.

     A chain-ending **zero results** is the one exception: an empty result set that web search
     also confirms is evidence of unavailability, so it takes the sold-out path below
     (`available: false`), not an unverified entry.
   - **Pasted** (`source: "pasted"`): no live re-query is possible — ask the user to re-paste,
     or skip with a note.
   Every trip kind must land in one of the three branches above; none may fall through unhandled.
2. Pick the **baseline**: walk `price_history` backwards from the last entry and stop at the
   first whose `available` is not `null`; if every entry is unverified, use `original_snapshot`.
   Unverified entries carry no observation, so comparing against one would invent a change that
   never happened. Compare the new price/availability against that baseline.
3. Append a new `price_history` entry with `checked_at` set to now (ISO-8601, with offset).
   `schema_version` stays `1` — `unverified_reason` appears only on unverified entries. Entries
   never record the driver, regardless of trip kind or which driver produced the read.
4. Report per the thresholds below.

## Reporting thresholds

- **Price drop:** new price is **≥5% lower** than the step-2 baseline → report as a drop, showing
  € amount and % change from both the baseline and the original snapshot.
- **Price rise:** new price is **≥5% higher** than the step-2 baseline → report as a rise, same
  detail.
- **No material change:** difference is within ±5% → note "unchanged" in the summary but still
  record the entry.
- **Sold out / unavailable:** adapter or web search finds no matching listing, or explicitly
  reports unavailability → set `available: false` for that entry and report a **sold-out
  warning**, distinct from a price change. Keep watching (do not auto-remove) unless the user
  runs `/watch remove`.
- **Blocked/challenged read (browser-driven only):** the terminal condition defined above in
  "Re-check procedure" — `available: null` plus an `unverified_reason`. Reported as a **blocked
  read**, never as a sold-out warning.

## Removing a trip (`/watch remove`)

Delete `<DATA_ROOT>/watchlist/<slug>.json`. Confirm the slug and destination with the user before deleting.

## Scheduling

Playwright MCP is `/watch`'s default driver because it is the only one of the two that can run
unattended — `claude-in-chrome` needs an attended session and per-site extension permission, so
it cannot execute on a schedule. Scheduled/cron runs require the headless server already declared
in the repo's tracked `.mcp.json` (see `ARCHI.md` §7 for its argument list); a headed browser
cannot start where there is no display.
