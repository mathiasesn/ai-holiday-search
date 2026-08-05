---
name: trivago-search
description: Browser-driven stays source for /scrape that reads trivago.dk search results via either the claude-in-chrome or Playwright MCP tools, normalizing hotel cards into the adapter result record. Runs on every /scrape alongside stays-search (not only as its fallback), has its own multi-step fallback chain instead of the exit-code adapter protocol, and labels every price as a web-read estimate.
---

# Trivago Search

Browser-driven stays source used by `/scrape`. Unlike `.agents/skills/*/search.py` adapters,
this skill has no `search.py` and no exit code — it drives a browser, via either the
`claude-in-chrome` MCP tools (the user's real Chrome session) or the Playwright MCP tools (an
isolated headless context), to read a live trivago.dk results page, then normalizes what it
finds. It runs on every `/scrape`, alongside `stays-search`, not only when `stays-search` fails.

trivago has no public search API and is bot-protected, so this is intentionally a Markdown
procedure over a real browser rather than a portable Python adapter. No Python, no
credentials, no env vars, no login, no booking. Stays only — no flights, no cars.

## Driver model

Steps below are written as capabilities, each with the concrete tool that implements it today.
**This section is the single home of the driver contract** — `momondo-search` and
`booking-search` reference it rather than restating the table.

**Two drivers exist, and either can execute this procedure (and momondo-search's and
booking-search's):** `claude-in-chrome` and the Playwright MCP server. Defaults differ by
caller: `/scrape` defaults to `claude-in-chrome` (Playwright MCP is available as an opt-in);
`/watch` defaults to Playwright MCP, because it is the only driver that can run unattended.
`claude-in-chrome` needs an attended session plus per-site extension permission, so it cannot
run on a schedule — that is the sole reason the second driver exists. The shared rule for both
drivers: after 2-3 consecutive tool failures on any step, stop retrying and drop to the
fallback chain below (see there for the full trigger list).

The Playwright MCP server is declared in the tracked `../../.mcp.json` (see [../../ARCHI.md](../../ARCHI.md) §7 for
both servers' full argument lists). The tool names below were confirmed present in a connected
Playwright MCP session on 2026-07-26.

A walkthrough on 2026-07-26 reached the real trivago.dk through the Playwright driver but was
blocked before reading a results page, so no step below is read-confirmed against the live site
— see [issue #8](https://github.com/mathiasesn/ai-holiday-search/issues/8) and [issue #9](https://github.com/mathiasesn/ai-holiday-search/issues/9).

| Capability | `claude-in-chrome` tool | Playwright MCP tool |
|---|---|---|
| Set up a tab / context | `tabs_context_mcp`, `tabs_create_mcp` | `browser_tabs` |
| Open a results page for known params | `navigate` to the constructed URL | `browser_navigate` |
| Fill and drive the search form | `form_input` (fields), `computer` (clicks: autocomplete suggestion, calendar days, Apply, Search) | `browser_fill_form`, `browser_type`, `browser_click`, `browser_select_option`, `browser_press_key` |
| Enumerate result cards | `find` (see "Reading result cards" below) | `browser_find` (fall back to `browser_snapshot`) |
| Read a page's structure/text | `read_page`; `get_page_text` for a single card only | `browser_snapshot` |
| Wait for results to render | (implicit in the read tools) | `browser_wait_for` |
| Detect a bot challenge / dead end | `read_page` or `get_page_text` on the loaded page | `browser_snapshot` (plus `browser_console_messages` when a page renders blank) |
| Capture evidence for a report | `gif_creator` / screenshots | `browser_take_screenshot` |

**Never use** `browser_evaluate` or `browser_run_code_unsafe`. Both execute arbitrary JS in the
page and exceed the read-only-navigation etiquette this skill (and momondo-search and
booking-search) commit to under "Limits and etiquette".

**Why these Playwright flags:**

- `--headless`: a scheduled/cron run has no display; a headed browser cannot start there. This
  flag is what makes the scheduling claim above actually true. The tracked `../../.mcp.json` also
  declares a second, headed `playwright-headed` server for attended debugging — see [../../ARCHI.md](../../ARCHI.md)
  §7 for the recipe and both servers' config; this file only needs the hazard note that follows.
- `--isolated`: a fresh profile per run, no persisted cookies or login state. This side-steps
  the privacy hazard in step 3 below (the homepage prefills the user's previous search and
  shows their recently-viewed properties) — an isolated context has no such history to leak.
  Trade-off: consent/cookie walls appear on every run and bot-challenge risk rises, which is
  why the unattended terminal outcome below is defined.
- `--user-agent` with an ordinary Chrome UA: **required for trivago specifically.** Headless
  Chrome's default UA advertises `HeadlessChrome`, which trivago's edge 403s at the document
  level, so no in-page workaround can recover it (fallback-chain condition 4). Set on the
  server, so no procedure step needs to know. Evidence and per-source scope:
  [issue #8](https://github.com/mathiasesn/ai-holiday-search/issues/8).

### Unattended terminal outcome

Under an unattended re-check (Playwright MCP, driven by `/watch`) there is no user to answer a
bot challenge, consent wall, or disambiguation prompt, so the attended tail of the fallback
chain below — step 8 and the disambiguation step 4 — is unavailable. The authoritative
definition of the resulting terminal outcome (fall through to web search, then record an
unverified `price_history` entry, reported distinctly from a genuine sold-out) lives in
[../price-watch/SKILL.md](../price-watch/SKILL.md)'s re-check procedure — this skill follows it rather than
restating the entry shape, which is that file's to change. One trivago-specific note: an ambiguous destination with
no known `locationId` in hand cannot be resolved unattended and takes that same terminal outcome
rather than guessing among the candidates.

## Locating a results page

### Primary path: drive the form (always works cold)

trivago's `locationId` (see URL grammar below) cannot be derived from a city name — it only
comes from the site's own autocomplete. Always drive the form unless a known `locationId` is
already in hand (see "Fast path" below).

1. Check the extension connection and site permission once per run (not per destination — see
   "Fallback chain" below), then `tabs_context_mcp`, `tabs_create_mcp` a **new** tab, `navigate`
   to `https://www.trivago.dk`.
2. Handle load-time overlays first: decline any non-essential-cookies banner if shown (a
   consented profile may show none), and dismiss any "Create account" promo overlay.
3. **Privacy hazard — read before typing anything.** The homepage shows the user's own
   "Recently viewed" properties and **prefills the search form with their previous search**
   (destination, dates, guest counts). Do not treat any of this as a search result. Overwrite
   every field explicitly rather than trusting what's prefilled — never submit on the assumption
   a field already holds the right value. Never copy any recently-viewed property, prefilled
   form value, or other observed account/browsing-history artifact into `details`, into any
   result record, or into presented output — this holds even though `<DATA_ROOT>/trip_scraper/` is
   gitignored; the hazard is exposure to the user's own session, not git tracking.
4. Type the destination into the search field. This opens an autocomplete dropdown — **you
   must click a suggestion; typing and submitting without clicking is not a valid search.**
   Ambiguous names return multiple options (a verified example: "Lisbon" returned Lisbon
   Portugal, a Lisbon coast region, and three unrelated US towns named Lisbon). If the intended
   match isn't unambiguous from the traveler's request, ask the user rather than guessing —
   **attended-only**: unattended, an ambiguous destination cannot be resolved this way, and
   takes the unattended terminal outcome above unless a known `locationId` is already in hand.
   Once resolved, record the destination's `locationId` (see URL grammar below) for the
   remainder of this run, so any additional destinations already resolved this run can use the
   fast path below instead of repeating disambiguation. This is in-conversation only — still no
   writing to `<DATA_ROOT>/profile/`.
5. Selecting the destination auto-opens the date picker (two months shown side by side, `<`/`>`
   to page). Click the check-in day, then the check-out day.
6. That auto-opens the Guests and rooms panel: Adults / Children / Rooms steppers and a "Pet
   friendly" checkbox. If Children > 0, a **"Children's ages (Required)"** control appears —
   every child needs an age selected or the search cannot proceed. Pull child ages from the
   traveler profile; never leave this blank.
7. Click Apply, then click Search.

### Fast path: construct the URL directly (only with a known locationId)

Skip the form only when the numeric `locationId` for the destination is already known — either
from earlier in this conversation (see "capture" note above), or already recorded by the
traveler in `<DATA_ROOT>/profile/search-queries.md` (gitignored — it may not exist in a fresh clone; read
it, never write it). Never fabricate a `locationId` — a wrong one silently returns the wrong
city. If the ID is not known, use the form path; if the user wants the discovered ID
persisted, tell them to add it via `/setup`.

This URL shape was captured live against trivago.dk on 2026-07-25, for Lisbon:

```
https://www.trivago.dk/en-US/lm/hotels-lisbon-portugal?search=200-31720;dr-20260914-20260919;drs-40;rc-1-2
```

| Segment/token | Meaning |
|---|---|
| `/en-US/` | Locale segment (English UI, `.dk` domain, DKK currency) |
| a Danish locale segment | Presumed to exist alongside `/en-US/`. **Unverified — do not assume its shape.** |
| `/lm/hotels-<city>-<country>` | Destination slug, verified for Lisbon, Portugal |
| `search=` | Semicolon-delimited token list |
| `200-<locationId>` | `200` = city concept type, `<locationId>` = opaque numeric ID (`31720` for Lisbon); verified for this one ID only — never derive an ID from a name |
| `dr-YYYYMMDD-YYYYMMDD` | Check-in/check-out (verified 2026-09-14 to 2026-09-19) |
| `rc-<rooms>-<adults>` | Rooms and adults, e.g. `rc-1-2` = 1 room, 2 adults |
| `drs-40` | **Unverified — meaning unknown; preserve as observed, do not invent a meaning.** |

This URL shape can rot (see "Limits and etiquette"). If a constructed URL misbehaves — wrong
city, no results, obviously stale layout — fall back to the form path rather than debugging the
URL further; drive the form in the already-open tab rather than starting over from a new tab.

## Reading result cards

- **Use `find` to enumerate result cards** (query for hotel result cards/articles). Verified:
  it returned all 40 loaded cards as `<article>` refs with name, star rating, and price. Fall
  back to `read_page` (accessibility tree) only if `find` returns nothing — don't run both by
  default, that costs a redundant full-page read per destination. Prefer refs over pixel
  coordinates generally.
- **Do not use `get_page_text` to enumerate results** — verified it returns only a single card
  (it targets `<article>` and prioritizes one), so it will silently under-report a list.
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
`<DATA_ROOT>/trip_scraper/seen.json` — [../trip-scraper/SKILL.md](../trip-scraper/SKILL.md) is authoritative for all
three; read it for the full shapes and the dedupe rules, plus the cross-source duplicate
presentation rule (one row per source, score-once) for when the same property also surfaces via
another enabled source. Only the trivago-specific field mappings are given here:

- `source`: literal `"trivago-search"`.
- `title`: the hotel name from the card.
- `price`: the **stay total**, read from the "kr N total" line (see price trap above) — never
  the per-night headline number.
- `currency`: `"DKK"` — what the page reads. Per
  [../holiday-planner/05-budget-rules.md](../holiday-planner/05-budget-rules.md) (EUR primary, DKK noted), also present a
  EUR-converted figure and label it a **conversion estimate** (rate not pinned to a live source)
  on top of the existing web-read-estimate label.
- `price_per_person`: the stay total (`price` above) divided by the adult count used in the
  search — the `<adults>` value from the `rc-<rooms>-<adults>` URL token. State this divisor
  plainly wherever `price_per_person` is shown; never leave the divisor implied.
- `dates`: `{"check_in": "<YYYY-MM-DD>", "check_out": "<YYYY-MM-DD>"}` from the search performed.
- `details`: free-form — per-night price, star rating, review score/count, distance to city
  centre, deal provider, alternative provider prices, badges, amenity highlights.
- `url`: the card's own deep link if present, else the results page URL.

## Fallback chain

None of these steps may error out a `/scrape` run — always degrade to the next step:

Any of these conditions ends the browser attempt and drops straight to the web-search fallback:

1. The driver is unavailable per its own readiness check, checked once per run, not per
   destination — for `claude-in-chrome`, the extension not connected or `tabs_context_mcp`
   showing no usable tab; for the Playwright MCP server, it not being connected.
2. Site permission for trivago.dk denied in the extension (`claude-in-chrome` only; the
   Playwright MCP server has no equivalent per-site permission step). Also checked once per run.
3. Bot challenge detected on the loaded page — stop navigating that page immediately.
4. The document itself came back non-200 (`403`/`429`). Chain-ends **immediately**: no retries,
   no re-navigation, no consent-wall handling. An edge rejection lands before any page script
   runs, so nothing done in-page can recover it, and retrying only spends calls against a host
   that is already refusing. Do not confuse this with condition 5 — a 403 page loads fine and is
   perfectly readable, it just isn't the results page.
5. Page unreadable (both a targeted element search and a full page read fail, or 2-3 consecutive
   tool failures).
6. Zero results for the given params.

Then, in order:

7. **Fallback: Claude web search** with the same destination/dates/guests, normalized into the
   same result record with `source: "trivago-search"` (or a clearly labeled web-search variant
   if the orchestrating skill distinguishes provenance).
8. **Final fallback: ask the user to paste listing text** (a specific hotel page, email, or
   screenshot-derived text), per `CLAUDE.md`'s paste-anything fallback and
   [../trip-scraper/SKILL.md](../trip-scraper/SKILL.md)'s "Paste-a-listing fallback" section — this enters the
   same normalize → dedupe → score pipeline as any other candidate, but takes `"source":
   "pasted"`, **not** `"trivago-search"` (per that section; `source` feeds the dedupe key hash).
   **Attended-only** — there is no user to ask on an unattended run; see "Unattended terminal
   outcome" above for the substitute behavior.

## Estimate labeling

Every price and availability figure this skill produces is a **web-read estimate, verify at
booking** — never present it as confirmed. trivago is metasearch: its prices routinely exclude
taxes, resort fees, and city taxes that the underlying booking site adds later.

## Limits and etiquette

- Read-only navigation of ordinary trivago.dk search-result pages, in the user's own browser
  session, at normal human-paced request volume. No aggressive polling, no scripted request
  volume, no booking, payment, or account-login automation.
- The DOM structure and the `search=` URL param grammar above are expected to drift over time,
  since they were captured from a single live session (see point-of-use guidance above for what
  to do when they do).
