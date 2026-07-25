---
name: trivago-search
description: Browser-driven stays source for /scrape that reads trivago.dk search results via the claude-in-chrome MCP tools, normalizing hotel cards into the adapter result record. Runs on every /scrape alongside stays-search (not only as its fallback), has its own multi-step fallback chain instead of the exit-code adapter protocol, and labels every price as a web-read estimate.
---

# Trivago Search

Browser-driven stays source used by `/scrape`. Unlike `.agents/skills/*/search.py` adapters,
this skill has no `search.py` and no exit code — it drives the user's real Chrome session via
`claude-in-chrome` MCP tools to read a live trivago.dk results page, then normalizes what it
finds. It runs on every `/scrape`, alongside `stays-search`, not only when `stays-search` fails.

trivago has no public search API and is bot-protected, so this is intentionally a Markdown
procedure over a real browser rather than a portable Python adapter. No Python, no
credentials, no env vars, no login, no booking. Stays only — no flights, no cars.

## Driver model

Steps below are written as capabilities, each with the concrete tool that implements it today.

**Default driver: `claude-in-chrome`.** Before first use, call `tabs_context_mcp`, then always
create a **new** tab with `tabs_create_mcp` rather than reusing an existing one. Never trigger
JS dialogs. After 2-3 consecutive tool failures on any step, stop retrying and drop to the
fallback chain below.

| Capability | `claude-in-chrome` tool |
|---|---|
| Open a results page for known params | `navigate` to the constructed URL |
| Fill and drive the search form | `form_input` (fields), `computer` (clicks: autocomplete suggestion, calendar days, Apply, Search) |
| Enumerate result cards | `find` (see "Reading result cards" below) |
| Read a page's structure/text | `read_page`; `get_page_text` for a single card only |
| Detect a bot challenge / dead end | `read_page` or `get_page_text` on the loaded page |

**Substitutable driver.** A Playwright-MCP-backed driver could replace `claude-in-chrome` for
the same capability list, and would specifically enable *unattended* `/watch` re-checks (the
`claude-in-chrome` extension needs an attended user session and site permission, so it cannot
drive scheduled/background price re-checks). Such a driver would need to provide: opening a
URL in an isolated browser context, filling the same three form steps (destination
autocomplete, date range, guests/rooms), waiting for results to render, and returning either
the rendered DOM/text or an equivalent structured accessibility read for the same card fields
listed below. This skill does not define that second procedure — only the capability contract
a substitute driver must satisfy.

## Locating a results page

### Primary path: drive the form (always works cold)

trivago's `locationId` (see URL grammar below) cannot be derived from a city name — it only
comes from the site's own autocomplete. Always drive the form unless a known `locationId` is
already in hand (see "Fast path" below).

1. `tabs_context_mcp`, then `tabs_create_mcp` a **new** tab, `navigate` to `https://www.trivago.dk`.
2. Handle load-time overlays first: decline any non-essential-cookies banner if shown (a
   consented profile may show none), and dismiss any "Create account" promo overlay.
3. **Privacy hazard — read before typing anything.** The homepage shows the user's own
   "Recently viewed" properties and **prefills the search form with their previous search**
   (destination, dates, guest counts). Do not treat any of this as a search result. Overwrite
   every field explicitly rather than trusting what's prefilled — never submit on the assumption
   a field already holds the right value.
4. Type the destination into the search field. This opens an autocomplete dropdown — **you
   must click a suggestion; typing and submitting without clicking is not a valid search.**
   Ambiguous names return multiple options (a verified example: "Lisbon" returned Lisbon
   Portugal, a Lisbon coast region, and three unrelated US towns named Lisbon). If the intended
   match isn't unambiguous from the traveler's request, ask the user rather than guessing.
5. Selecting the destination auto-opens the date picker (two months shown side by side, `<`/`>`
   to page). Click the check-in day, then the check-out day.
6. That auto-opens the Guests and rooms panel: Adults / Children / Rooms steppers and a "Pet
   friendly" checkbox. If Children > 0, a **"Children's ages (Required)"** control appears —
   every child needs an age selected or the search cannot proceed. Pull child ages from the
   traveler profile; never leave this blank.
7. Click Apply, then click Search.

### Fast path: construct the URL directly (only with a known locationId)

Skip the form only when the numeric `locationId` for the destination is already known — from
earlier in this conversation, or recorded in `profile/search-queries.md` (gitignored, so it's a
safe place to keep a bare numeric city ID; that ID alone is not personal data). Never fabricate
a `locationId` — a wrong one silently returns the wrong city. If the ID is not known, use the
form path and consider recording the ID discovered afterward.

**Verified URL shape** (captured live against trivago.dk on 2026-07-25, for Lisbon):

```
https://www.trivago.dk/en-US/lm/hotels-lisbon-portugal?search=200-31720;dr-20260914-20260919;drs-40;rc-1-2
```

| Segment/token | Meaning | Status |
|---|---|---|
| `/en-US/` | Locale segment (English UI, `.dk` domain, DKK currency) | Verified |
| a Danish locale segment | Presumed to exist alongside `/en-US/` | **Unverified — do not assume its shape** |
| `/lm/hotels-<city>-<country>` | Destination slug | Verified for Lisbon, Portugal |
| `search=` | Semicolon-delimited token list | Verified |
| `200-<locationId>` | `200` = city concept type, `<locationId>` = opaque numeric ID (`31720` for Lisbon) | Verified for this one ID; never derive an ID from a name |
| `dr-YYYYMMDD-YYYYMMDD` | Check-in/check-out | Verified (2026-09-14 to 2026-09-19) |
| `rc-<rooms>-<adults>` | Rooms and adults, e.g. `rc-1-2` = 1 room, 2 adults | Verified |
| `drs-40` | Unknown meaning | **Unverified — preserve as observed, do not invent a meaning** |

This URL shape can rot (see "Limits and etiquette"). If a constructed URL misbehaves — wrong
city, no results, obviously stale layout — fall back to the form path rather than debugging the
URL further.

## Reading result cards

- **Use `find` to enumerate result cards** (query for hotel result cards/articles). Verified:
  it returned all 40 loaded cards as `<article>` refs with name, star rating, and price.
- **Do not use `get_page_text` to enumerate results** — verified it returns only a single card
  (it targets `<article>` and prioritizes one), so it will silently under-report a list.
- `read_page` (accessibility tree) is a viable alternative extraction path. Prefer text/a11y
  extraction over coordinate clicking generally, and prefer refs over pixel coordinates.
- Ignore non-hotel promotional cards interleaved with results (observed example: "Haven't found
  a good match yet?").
- Ignore "Sign in to unlock" member-only prices entirely — this skill never logs in, so never
  report a price that's only visible behind sign-in. Use the public price shown on the card.

**Per card, extract:**

- Name, star rating, review score and count (e.g. `8.7 Excellent (9,755 ratings)`).
- **Per-night price (the large headline number) and the separate "kr N total" line** — see the
  price trap below; both are read, but they map to different output fields.
- Distance to city centre, amenity highlights.
- Deal provider (e.g. `Hotel Site`, `Hotels.com`, `Super.com`, `Priceline`) and any alternative
  provider prices listed under the main deal.
- Badges present (e.g. `Our lowest price`, `15% lower than other sites`, `Free cancellation
  before <date>`, `No prepayment needed`, `Loyalty deal`), and `Actual price` vs a struck-through
  `Previous price` if shown.
- The results header count if present (observed example: "We found 1000+ hotels from 192
  sites") — informational only, not per-card data.

### The price trap (critical)

The large, prominent price on a trivago card is the **per-night** price, not the stay total.
The total appears separately as a "kr N total" line. Verified twice on 2026-07-25: `kr 1,297`
per night / `kr 6,485 total` over 5 nights (1297 x 5 = 6485), and `kr 1,756` / `kr 8,778 total`.
**Always read the "total" line for the result record's `price` field — never the headline
number.** Record the per-night figure under `details`, it is not discarded, just not the
primary price.

## Normalization

This skill does not define the adapter result record, the normalized candidate record, or
`trip_scraper/seen.json` — `.claude/skills/trip-scraper/SKILL.md` is authoritative for all
three; read it for the full shapes and the dedupe/collapsing rules. Only the trivago-specific
field mappings are given here:

- `source`: literal `"trivago-search"`.
- `price`: the **stay total**, read from the "kr N total" line (see price trap above) — never
  the per-night headline number.
- `currency`: `"DKK"`.
- `dates`: `{"check_in": "<YYYY-MM-DD>", "check_out": "<YYYY-MM-DD>"}` from the search performed.
- `details`: free-form — per-night price, star rating, review score/count, distance to city
  centre, deal provider, alternative provider prices, badges, amenity highlights.
- `url`: the card's own deep link if present, else the results page URL.

## Fallback chain

None of these steps may error out a `/scrape` run — always degrade to the next step:

Any of these conditions ends the browser attempt and drops straight to the web-search fallback:

1. Extension not connected, or `tabs_context_mcp` shows no usable tab.
2. Site permission for trivago.dk denied in the extension.
3. Bot challenge detected on the loaded page — stop navigating that page immediately.
4. Page unreadable (both `find` and `read_page` fail, or 2-3 consecutive tool failures).
5. Zero results for the given params.

Then, in order:

6. **Fallback: Claude web search** with the same destination/dates/guests, normalized into the
   same result record with `source: "trivago-search"` (or a clearly labeled web-search variant
   if the orchestrating skill distinguishes provenance).
7. **Final fallback: ask the user to paste listing text** (a specific hotel page, email, or
   screenshot-derived text), per `CLAUDE.md`'s paste-anything fallback — this enters the same
   normalize → dedupe → score pipeline as any other candidate.

## Estimate labeling

Every price and availability figure this skill produces is a **web-read estimate, verify at
booking** — never present it as confirmed. trivago is metasearch: its prices routinely exclude
taxes, resort fees, and city taxes that the underlying booking site adds later.

## Limits and etiquette

- Read-only navigation of ordinary trivago.dk search-result pages, in the user's own browser
  session, at normal human-paced request volume. No aggressive polling, no scripted request
  volume, no booking, payment, or account-login automation.
- The DOM structure and the `search=` URL param grammar above are expected to drift over time
  since they were captured from one live session — prefer the form-driven path whenever the
  constructed URL misbehaves rather than trying to patch the URL grammar.
- Every concrete example in this file (the Lisbon URL and `locationId`, the two price-trap
  figures, the card badges) was captured from a single browser session on 2026-07-25. They
  illustrate structure only — they are not current pricing or availability, and must never be
  presented as live data in an actual `/scrape` run.
