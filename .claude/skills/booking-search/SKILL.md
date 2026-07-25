---
name: booking-search
description: Browser-driven stays/flights source for /scrape that reads booking.com search results via the claude-in-chrome MCP tools, normalizing hotel and flight cards into the adapter result record. Covers two verticals (stays, flights) as parallel procedures sharing one browser session and one permission check per run, each with its own independent fallback chain, and labels every price as a web-read estimate.
---

# Booking Search

Browser-driven source used by `/scrape`. Like `trivago-search` and `momondo-search`, this skill
has no `search.py` and no exit code — it drives the user's real Chrome session via
`claude-in-chrome` MCP tools to read live booking.com results pages, then normalizes what it
finds. It runs on every `/scrape`, alongside the CLI adapters, not only when they fail.

booking.com has no openly available search API (its Demand API is partner-gated) and is
bot-protected, so this is intentionally a Markdown procedure over a real browser rather than a
portable Python adapter. No Python, no credentials, no env vars, no login, no booking, no
payment, no Genius-account automation.

booking.com covers **two verticals** relevant here — stays and flights — as parallel procedures
inside this one skill. **There is no packages vertical**; see "Packages (verified absent)" below.
Attractions and car hire are out of scope entirely (not `/scrape` source categories).

All findings below were captured live against booking.com on **2026-07-25**, single session, via
`claude-in-chrome`, Danish UI (`index.da.html`, `lang=da`), currency manually switched to **DKK**
(persists across pages once set). Not logged in throughout. Sample query: Lisbon, 2 adults,
2026-10-14 to 2026-10-19, origin Copenhagen for flights. Anything not directly observed in that
session is marked UNVERIFIED below and must not be treated as fact.

## Vertical selection

Which of the two verticals run is **query-driven, not always-on** — the rule is authoritative in
`.claude/skills/trip-scraper/SKILL.md` ("Vertical selection"); do not restate it here. This
skill's obligation under it: run only the verticals it was asked for, name which ones ran, say
plainly which were skipped, and ask when ambiguous.

Stays and flights share **one browser session and one permission/connection check per run**
(checked once, not once per vertical). Each vertical then falls back **independently** through the
chain below — a bot challenge on flights must not suppress stays.

## Driver model

Steps below are written as capabilities, each with the concrete tool that implements it today.

**Default driver: `claude-in-chrome`.** Standard Chrome-automation guidance (tab/context setup, no
JS dialogs, etc.) applies as usual; the one skill-specific rule is: after 2-3 consecutive tool
failures on any step, stop retrying and drop to that vertical's fallback chain below.

| Capability | `claude-in-chrome` tool |
|---|---|
| Open a results page for known params | `navigate` to the constructed URL |
| Fill and drive a search form | `form_input` (fields), `computer` (clicks: autocomplete suggestion, calendar days, occupancy/passenger steppers, Søg) |
| Enumerate result cards | `find` (see "Reading result cards" below) |
| Read a page's structure/text | `read_page`; `get_page_text` for a single card only |
| Detect a bot challenge / dead end | `find` (empty or challenge-shaped result) or `read_page` on the loaded page |

**Substitutable driver.** A Playwright-MCP-backed driver could satisfy the same capability table
above and would additionally enable *unattended* `/watch` re-checks, which `claude-in-chrome`
cannot do (it needs an attended user session and site permission) — the same design note recorded
in `.claude/skills/trivago-search/SKILL.md` ("Driver model"). This is a note recording a
deliberate design decision, not a spec for it.

## Privacy hazard — read before driving any form

**The flights form arrives prefilled** with an origin (verified: `København Alle lufthavne`) even
though the session was not logged in — treat any prefilled field the same as momondo/trivago's
account-history prefills: never trust it un-touched, verify it matches the traveler's actual
origin before submitting, and never copy a prefilled value, a recent search, a saved list, or any
other account/browsing-history artifact into `details` or any presented output. The stays vertical
was not observed showing a "recent searches" panel in this session, but treat any such panel that
does appear the same way.

## Reading result cards

Use `find` to enumerate result cards; fall back to `read_page` only if `find` returns nothing —
don't run both by default. **Never `get_page_text` to enumerate** — it under-reports a list, per
the same hazard documented for trivago and momondo. Ignore sponsored/promo-labelled and
interstitial cards, and treat any sign-in-gated ("Genius" / "Secret Deal") price as requiring an
account rather than a real comparable price — none were observed in this run (not logged in), but
one must be assumed possible.

## Stays

### Locating a results page

**No fast-path URL is available — always drive the form.** The results URL uses an opaque
`dest_id`/`dest_type` pair that cannot be derived from a place name (same hazard as momondo's
`-p<id>` and trivago's `locationId`), and no dead-end fast-path guess was even tested this run —
treat the query string below as reproducible only via the form, not hand-constructable.

1. Check the extension connection and site permission once per run, `tabs_context_mcp`,
   `tabs_create_mcp` a **new** tab, `navigate` to `https://www.booking.com/index.da.html`
   ("Overnatning" tab is default/active).
2. Type the destination into "Indtast destination". **Disambiguation hazard (verified):** typing
   "Lissabon" returns the city as the top match, but a sibling airport entry
   (`Lissabon Humberto Delgado Lufthavn`), an unrelated Dutch town, and a conference-centre entry
   all appear nearby. Read the subtitle and pick the city entry explicitly — never assume the
   first result is right.
3. Open the date field (two-month side-by-side calendar, `›` to page forward). **Verified UI
   quirk:** clicking a start date then an end date across a month boundary can silently land
   several nights short of what was intended. Reliable pattern: click the start date, re-open the
   calendar and click it again if the display looks wrong, then click the true end date, and
   **check the displayed range in the field before proceeding** rather than trusting the click
   sequence blindly.
4. Occupancy panel ("Vælg værelser og gæster") defaults to 2 adults / 0 children / 1 room; use the
   stepper for other counts (not exercised live this run beyond the default — treat as standard
   stepper UI).
5. Click "Søg".

Resulting URL, verified:

```
https://www.booking.com/searchresults.da.html?ss=Lissabon%2C+Lisbon+Region%2C+Portugal&dest_id=-2167973&dest_type=city&checkin=2026-10-14&checkout=2026-10-19&group_adults=2&no_rooms=1&group_children=0&lang=da&aid=304142&label=<opaque>&selected_currency=DKK&sb=1&...
```

| Param | Meaning | Status |
|---|---|---|
| `ss` | Destination display string | Verified |
| `dest_id` / `dest_type` | Opaque numeric place id + type (`city`) — cannot be derived from a name | Verified present; value opaque, never fabricate |
| `checkin` / `checkout` | `YYYY-MM-DD` | Verified |
| `group_adults` / `group_children` / `no_rooms` | Occupancy | Verified |
| `lang` | UI language | Verified |
| `selected_currency` | Currency override, added after manually switching currency | Verified |
| `aid`, `label`, `search_pageview_id`, `ac_meta`, `efdco`, `sb`, `src`, `src_elem`, `ac_position`, `ac_click_type`, `ac_langcode`, `ac_suggestion_list_length` | Affiliate/tracking/autocomplete telemetry | Present, opaque — don't strip or fabricate |

### Card fields

`find` ("hotel result card in the search results list") returned 20+ cards cleanly in one call, no
`read_page` fallback needed. No sponsored-labelled cards were observed this run (not proof none
exist).

Per card, extract: hotel name, star rating, review score badge + count (e.g. "9,0 Fabelagtigt"),
neighbourhood name, distance to centre (e.g. "1,7 km fra centrum"), room-type line, bed
configuration, perk badges ("Gratis afbestilling", "Inklusive morgenmad"), scarcity nudges, any
struck-through "was" price, and the "Se tilgængelighed" CTA. **No board-basis dropdown or
cross-provider price list on the card** — booking.com is a first-party listing, not metasearch, so
there is one price per card (unlike momondo's/trivago's multi-provider ladder).

### Price trap (verified)

The headline price is the **per-stay total for the full occupancy searched** (e.g. 2 adults × 5
nights) — there is **no per-night/per-stay toggle** on this page (checked via `find`; it reported
no such control). A card subtext reads "Inklusive skatter og gebyrer" (taxes and fees included) on
every card seen, so the headline appears to include taxes — but the exact tax composition **could
not be verified** beyond that inclusive label (verifying it requires proceeding toward checkout,
out of scope).

The `(i)` info icon opens a breakdown tooltip, verified example: `DKK 919,95 × 5 nætter = DKK
4.599,73`, then a discount line, then `I alt DKK 3.954,64`. **The headline card price already nets
out any shown discount — the per-night rate in the tooltip is pre-discount, so multiplying it by
nights does not reproduce the headline.** Always read the headline (or the tooltip's `I alt` line)
directly; never derive it by multiplying the per-night figure.

Whether a logged-in Genius member would see a different (lower) price **could not be verified**
(requires login, out of scope) — treat all-caps assumptions about Genius pricing as unconfirmed.

## Flights

### Locating a results page

1. `navigate` to `https://www.booking.com/flights/index.da.html` (also reachable via the "Fly" nav
   tab on the homepage, same session).
2. Form defaults, verified: "Retur" (round-trip) radio pre-selected, cabin class defaults to
   Economy, a "Kun direkte fly" (direct-only) checkbox, and the origin field ("Afrejse fra")
   **arrives prefilled** with "København Alle lufthavne" — see the privacy hazard above, verify
   before trusting it un-touched.
3. Destination field ("Ankomst til"): type-ahead **only offered the airport**
   (`LIS Lissabon Humberto Delgado Lufthavn`) for "Lissabon" — unlike the stays field, no
   city-level option appeared. Don't expect a city choice here.
4. Date field: same two-month calendar and off-by-N-days risk as stays — re-verify the displayed
   range before submitting.
5. Passenger field ("Passagerer") defaults to 1 adult; use the `+`/`−` stepper panel to reach the
   needed count (verified working via direct `+` click).
6. Click "Søg".

**Domain handoff (verified):** submitting navigates to a **different subdomain**,
`flights.booking.com`, which shows its own fresh cookie-consent banner and renders in **English**,
not Danish, even though the originating session was on the `…da.html` homepage — UI language did
not carry over, but the DKK currency selection did.

Resulting URL, verified:

```
https://flights.booking.com/flights/CPH.CITY-LIS.AIRPORT/?type=ROUNDTRIP&adults=2&cabinClass=ECONOMY&children=&from=CPH.CITY&to=LIS.AIRPORT&fromCountry=DK&toCountry=PT&fromLocationName=K%C3%B8benhavn&toLocationName=Lissabon+Humberto+Delgado+Lufthavn&depart=2026-10-14&return=2026-10-19&sort=BEST&travelPurpose=leisure&ca_source=flights_index_sb&aid=304142&label=<opaque>
```

| Param | Meaning | Status |
|---|---|---|
| `<ORIGIN>.CITY-<DEST>.AIRPORT` (path) | Origin/destination tokens, suffixed `.CITY` or `.AIRPORT` by what was picked | Verified |
| `type` | `ROUNDTRIP` — `ONEWAY`/`MULTICITY` values implied by the form's radio options | UNVERIFIED for those two, only `ROUNDTRIP` observed |
| `adults` / `children` | Passenger counts | Verified |
| `cabinClass` | `ECONOMY` | Verified for this value only — other cabin tokens UNVERIFIED |
| `from` / `to`, `fromCountry` / `toCountry`, `fromLocationName` / `toLocationName` | Repeated place info | Verified |
| `depart` / `return` | `YYYY-MM-DD` | Verified |
| `sort` | `BEST`; page also offers Cheapest/Fastest tabs client-side | UNVERIFIED whether those change the `sort=` value — not checked |
| `travelPurpose` | `leisure`; alternate values | UNVERIFIED |
| `aid`, `label`, `ca_source` | Affiliate/tracking, opaque | Present |

### Card fields

Sort tabs: Best / Cheapest / Fastest (English labels). Left rail: Search summary, Stops filter,
Airlines filter with per-airline counts.

Per card, extract: outbound + return rows with departure/arrival times, airport codes, `Direct`/`N
stop` badge, leg duration, operating airline name, a baggage-icon pair (read as checked bag +
carry-on included, but the icons were not individually labelled in text — treat the exact
allowance as **could not verify without opening "View details"**), any "Flexible ticket upgrade"
tag, and "View details". No sponsored cards seen among those read.

Whether `flights.booking.com` is operated by Booking.com's own stack or a third party (e.g.
Etraveli) **could not be verified** from the UI (no attribution string visible, and checking would
require inspecting network requests beyond this skill's tools) — flag as unconfirmed wherever the
operating provider is stated.

### Price trap (verified — same inversion as momondo)

Headline price (e.g. `DKK 3,728`) is **per person**; a smaller line beneath reads `DKK 7,455
total`. The `(i)` icon opens a "Price details" popover, verified verbatim:

```
Price details
Flight (2 travelers)
Adults (2)        DKK 7,454.36
Total             DKK 7,454.36
Includes taxes and fees
```

**`price` must come from the total line / the popover's Total row — the large headline number is
per-person and must never be used as the trip price.** Taxes and fees are confirmed included in
that total.

## Packages (verified absent)

**Verified 2026-07-25: booking.com has no bundled flight+hotel package product.**
`https://www.booking.com/flight-hotel/index.da.html` returns "Siden kunne ikke findes" (404) — a
dead end, do not reuse it. The real "Fly + hotel" entry point is a tab on the ordinary homepage
that does **not** navigate anywhere — it only reveals a checkbox, "Tilføj flyrejser til min
søgning", on the same stays form. Searching with it checked produces two disconnected outcomes:
the main tab stays on the **ordinary stays results page** (`searchresults.da.html`, one extra
`sb_flight_search=flight` param, identical cards/prices to plain stays), and a **second tab**
auto-opens to `flights.booking.com` running an independent flight search that in this run defaulted
to the wrong origin airport (BLL instead of the previously-shown CPH). There is no shared reference
id, no combined URL, and no bundled per-trip total anywhere in this flow.

**`momondo-search` remains the packages source** (its `Pakkerejser` vertical returns real bundled
package cards with one total). This skill never synthesizes a stays+flights total into a package
price — if a combined figure is ever needed from booking.com it would have to be built manually by
running the stays and flights verticals separately and adding the two totals, and this skill does
not do that as part of normal operation. Do not re-investigate this finding; it is settled.

## Normalization

This skill does not define the adapter result record, the normalized candidate record, or
`trip_scraper/seen.json` — `.claude/skills/trip-scraper/SKILL.md` is authoritative for all three,
including the cross-source duplicate presentation rule (one row per source, scored once on the
lowest price) for when the same property/flight also surfaces via another enabled source. Only
booking-specific mappings are given here:

- `source`: literal `"booking-search"`.
- `title`: the hotel name / flight route from the card.
- `price`: always the **all-in total for the whole party/stay** — the stay-total headline for
  stays (already tax/fee-inclusive per the label observed), the Total line from the `(i)` popover
  for flights (never the per-person headline).
- `price_per_person`: present for flights, with the divisor (adult count used in the search)
  stated explicitly.
- `currency`: `"DKK"` — what the page reads. Per
  `.claude/skills/holiday-planner/05-budget-rules.md` (EUR primary, DKK noted), also present a
  EUR-converted figure and label it a **conversion estimate** (rate not pinned to a live source),
  on top of the web-read-estimate label below.
- `dates`: stays — `{"check_in": "<YYYY-MM-DD>", "check_out": "<YYYY-MM-DD>"}`; flights —
  `{"depart": "<YYYY-MM-DD>", "return": "<YYYY-MM-DD>"}`.
- `details`, per vertical:
  - stays: per-night price (reference only, never used to derive `price`), star rating, review
    score/count, distance to centre, room type, board basis, cancellation policy, taxes-included
    flag.
  - flights: carriers, stops, layover durations, total duration, fare brand, operating/booking
    provider (flag as unconfirmed per the note above), baggage note (flag exact allowance as
    could-not-verify per the card-fields note above).
- `url`: the card's own deep link if present, else the results page URL.

**Overlap with `trivago-search`/`momondo-search` on stays, or `momondo-search` on flights:** when
the same property or flight is surfaced by more than one source, present **one linked row per
source**, each with its own price and `source`, visibly grouped as the same underlying item, price
gap noted as further evidence all figures are estimates. Score and rank the group **once**, using
the lowest of the quoted prices — see `.claude/skills/trip-scraper/SKILL.md` for the shared
candidate record this relies on.

## Fallback chain

None of these steps may error out a `/scrape` run — always degrade to the next step. Stays and
flights fall back **independently** — a failure on one never suppresses the other.

Any of these conditions ends the browser attempt for that vertical and drops straight to the
web-search fallback:

1. Extension not connected, or `tabs_context_mcp` shows no usable tab. Checked once per run
   (shared across both verticals), not once per vertical.
2. Site permission for booking.com denied in the extension. Also checked once per run.
3. Bot challenge detected on the loaded page — stop navigating that page immediately.
4. Page unreadable (both `find` and `read_page` fail, or 2-3 consecutive tool failures).
5. Zero results for the given params.

Then, in order, for the affected vertical only:

6. **Fallback: Claude web search** with the same params, normalized into the same result record
   with `source: "booking-search"` (or a clearly labeled web-search variant if the orchestrating
   skill distinguishes provenance).
7. **Final fallback: ask the user to paste listing text** (a specific hotel/flight page, email, or
   screenshot-derived text), per `CLAUDE.md`'s paste-anything fallback and
   `.claude/skills/trip-scraper/SKILL.md`'s "Paste-a-listing fallback" section — this enters the
   same normalize → dedupe → score pipeline as any other candidate, but takes `"source":
   "pasted"`, **not** `"booking-search"` (per that section; `source` feeds the dedupe key hash).

## Estimate labeling

Every price and availability figure this skill produces is a **web-read estimate, verify at
booking** — never present it as confirmed. booking.com headline rates routinely exclude city tax
and can vary by logged-in Genius status, and the flights vertical hands off to a possibly
third-party-operated subdomain whose fare rules aren't guaranteed to match what's shown here.

## Limits and etiquette

- Read-only navigation of ordinary booking.com search-result pages, in the user's own browser
  session, at normal human-paced request volume. No aggressive polling, no scripted request
  volume, no booking, payment, or account-login automation.
- The DOM structure and the URL grammars above are expected to drift over time, since they were
  captured from a single live session on 2026-07-25 (see point-of-use guidance above for what to
  do when they do).
- No packages vertical, no attractions, no car hire — out of scope per the spec.
