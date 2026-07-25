---
name: momondo-search
description: Browser-driven flights/stays/packages source for /scrape that reads momondo.dk search results via the claude-in-chrome MCP tools, normalizing flight, hotel, and package cards into the adapter result record. Covers three verticals (flights, stays, packages) as parallel procedures sharing one browser session and one permission check per run, each with its own independent fallback chain, and labels every price as a web-read estimate.
---

# Momondo Search

Browser-driven source used by `/scrape`. Like `trivago-search`, this skill has no `search.py`
and no exit code — it drives the user's real Chrome session via `claude-in-chrome` MCP tools to
read live momondo.dk results pages, then normalizes what it finds. It runs on every `/scrape`,
alongside the CLI adapters, not only when they fail.

momondo has no public search API and is bot-protected, so this is intentionally a Markdown
procedure over a real browser rather than a portable Python adapter. No Python, no credentials,
no env vars, no login, no booking, no payment.

Unlike `trivago-search` (stays only), momondo.dk exposes four verticals on its homepage tabs:
`Fly` (flights), `Overnatning` (stays), `Billeje` (cars), and `Pakkerejser` (packages). This
skill covers **flights, stays, and packages** as three parallel procedures. **Cars are never
run** — out of scope per the spec.

## Vertical selection

Which of the three verticals run is **query-driven, not always-on** — the rule is authoritative
in `.claude/skills/trip-scraper/SKILL.md` ("Vertical selection"); do not restate it here. This
skill's obligation under it: run only the verticals it was asked for, and name which ones ran.

The three verticals share **one browser session and one permission/connection check per run**
(checked once, not once per vertical). Each vertical then falls back **independently** through
the chain below — a bot challenge on flights must not suppress stays or packages.

## Driver model

Steps below are written as capabilities, each with the concrete tool that implements it today.

**Default driver: `claude-in-chrome`.** Standard Chrome-automation guidance (tab/context setup,
no JS dialogs, etc.) applies as usual; the one skill-specific rule is: after 2-3 consecutive
tool failures on any step, stop retrying and drop to that vertical's fallback chain below.

| Capability | `claude-in-chrome` tool |
|---|---|
| Open a results page for known params | `navigate` to the constructed URL |
| Fill and drive a search form | `form_input` (fields), `computer` (clicks: autocomplete suggestion, calendar days, checkboxes, Søg) |
| Enumerate result cards, and detect a bot challenge / dead end | `find` (see "Reading result cards (all verticals)" below) |
| Read a page's structure/text | `read_page`; `get_page_text` for a single card only |

**Substitutable driver.** The Playwright-MCP substitution note in
`.claude/skills/trivago-search/SKILL.md` ("Driver model") applies here unchanged.

## Privacy hazard — read before driving any form

**The user is signed in on momondo.dk.** The homepage and every vertical landing page show a
`Dine seneste søgninger` (your recent searches) section with real prior trips, and the search
form itself **arrives prefilled from the user's own search history** (origin, destination,
dates, traveller count). Params also carry across verticals within a session — a stays form was
observed prefilled from a preceding flight search.

- Never treat any recent search, prefilled field, or cross-vertical carryover as a result.
- Overwrite every field explicitly rather than trusting a prefill — never submit assuming a
  field already holds the right value.
- Never copy a recent search, prefilled value, or any other account/browsing-history artifact
  into `details`, into any result record, or into presented output.

This applies to all three verticals below.

## Side effects to watch for (all verticals)

- The stays and packages forms carry a pre-checked **"Sammenlign momondo med …"** checkbox
  (`Booking.com` for stays, `lastminute.com` for packages). Uncheck it before searching —
  leaving it checked makes the search button open a **second tab on that third-party site**. If
  a second tab appears anyway, ignore it; never read results from it.
- Promo/ad cards are interleaved with results, always marked `Annonce` (observed: an `AVIS`
  car-rental ad in flights, a `lastminute.com` ad in packages). Ignore them.
- Non-blocking overlays can appear (`Få prisopdateringer` price-tracking prompt, a `Del
  feedback?` survey). Dismiss or ignore. **Never enable price tracking** — that creates a
  standing subscription on the user's account, which this skill must not do.
- Results load progressively (a `Henter` loading indicator sits in the left rail and fares
  re-sort as they stream in). Wait for it to finish before reading cards, or the cheapest price
  read will be wrong.

## Reading result cards (all verticals)

Use `find` to enumerate result cards; fall back to `read_page` only if `find` returns nothing —
don't run both by default, that costs a redundant full-page read per vertical. **Never
`get_page_text` to enumerate** — it under-reports a list. `find`'s result is also the
bot-challenge check for that page load: if it comes back empty or challenge-shaped, that is the
signal to fall back, so no separate detection read is needed. Ignore `Annonce`-marked cards.

Each vertical's own section below lists only the fields to extract and its price trap.

All URL grammars, price traps, and page behaviors documented below were captured live against
momondo.dk on **2026-07-25**, from a single live session, and may drift — see "Limits and
etiquette".

## Flights

### Locating a results page

**Fast path (verified): construct the URL directly.** Unlike stays, flights need no opaque ID:

```
https://www.momondo.dk/flight-search/CPH-LIS/2026-09-14/2026-09-19/2adults?sort=price_a
```

| Segment/token | Meaning |
|---|---|
| `<ORIGIN>-<DEST>` | IATA codes |
| `/YYYY-MM-DD/YYYY-MM-DD` | Out/return dates |
| `/<N>adults` | Optional; omitted means 1 adult |
| `?sort=price_a` | Cheapest first; verified alongside `sort=bestflight_a` (momondo's "Bedst"). Other sort tokens are unverified — don't assume them. |

Multi-city/one-way URL grammar and any cabin-class token are **unverified** — do not guess them;
drive the form instead (`https://www.momondo.dk/flight-search` or the `Fly` tab, filling
origin/destination/dates/travellers, being careful to overwrite any prefill per the privacy
hazard above) if the trip needs either of those.

### Card fields

Result header tabs read `Billigst` / `Bedst` / `Hurtigst`, each showing a price + duration. A
results count reads like `240 af 240 fly`.

Per card, extract: carriers, stops, layover durations, total duration, fare brand, booking
provider, baggage note, and the price (see trap below).

### Price trap (verified)

With 2 adults, the large headline reads e.g. `925 kr. /person` with a smaller line beneath
reading `1.849 kr. i alt`. With 1 adult there is no `/person` suffix and no `i alt` line.

**`price` MUST come from the `i alt` (total) line whenever it is present.** The `/person`
headline maps to `price_per_person`, with the divisor stated explicitly (the adult count used in
the search).

## Stays

### Locating a results page

**No guessable URL grammar exists — the form path is primary.** Both of the following are
verified dead ends, so don't retry them:
- `https://www.momondo.dk/hotels/<city>/...` redirects to `/stays`.
- `https://www.momondo.dk/stays/<city>/<dates>/2adults` returns a 404.

Drive the form from `https://www.momondo.dk/stays`: fill destination (watch for the
disambiguation hazard below), dates, and travellers, uncheck the "Sammenlign momondo med
Booking.com" box (see side effects above), then click `Søg`.

The resulting URL is observed to look like:

```
https://www.momondo.dk/hotel-search/Lissabon,Lissabon,Portugal-p178681/2026-09-14/2026-09-19/2adults;map?ucs=6m4d89&sort=rank_a
```

`-p178681` is an opaque place ID that **cannot be derived from a name** — the same hazard as
trivago's `locationId`. Never fabricate one. `ucs=` is an opaque session token — unverified,
never fabricate it either. `;map` opens the map pane. Once observed for a destination this URL
may be reused as a fast path later in the same run, exactly like trivago's locationId capture
rule — this is in-conversation only, never written to `profile/`.

**Disambiguation hazard (verified):** typing a city name can resolve to the *airport* instead of
the city — the verification run resolved "Lissabon" to `Lissabon Humberto Delgado Lufthavn
(LIS)`. Check what the form actually resolved to before trusting results; ask the user when
ambiguous. Resolve a given destination **once per run**: once the user has confirmed which
match is intended, reuse that answer for the other verticals in the same run rather than
re-asking or re-disambiguating per vertical.

### Card fields

Per card, extract: hotel name, `N km fra centrum`, review score + label + count (e.g. `8,8 Meget
god (4460)`), star rating, the main provider offer (e.g. `Booking.com 1.159 kr.`) with its `Se
tilbud` link, alternative provider rows beneath (e.g. `Hotels.com`, `agoda`, `stayforlong`) each
with their own price, and perks (`Gratis afbestilling`, `Gratis morgenmad`).

### Price trap (verified — worse than trivago's)

A price-basis dropdown above the results reads `Pris: …` with three options:

- `Ophold i alt – Inklusive alle skatter + afgifter` (stay total, all taxes and fees)
- `Pr. nat inklusive moms – Grundpris pr. nat inkl. moms` (**the default**)
- `I alt pr. nat – Inklusive alle skatter + afgifter`

**Switch this dropdown to `Ophold i alt` before reading any price.** Verified: one property
showed `1.159 kr.` under the default and `6.093 kr.` under `Ophold i alt` for a 5-night stay —
note 5 × 1.159 = 5.795, not 6.093, so the total includes fees the per-night base price omits.
**Multiplying the per-night figure yourself gives the wrong number — always read the switched
total directly.**

## Packages

### Locating a results page

Prefer the form path: `https://www.momondo.dk/pakkerejser`, filling destination/dates/travellers
(watch the privacy-hazard prefill), unchecking the "Sammenlign momondo med lastminute.com" box,
then `Søg`.

An observed URL for this vertical:

```
https://www.momondo.dk/packages/Lissabon-LIS-ALIS/2026-09-14/2026-09-19/-1,-1/2/-1,-1,-1/CPH?ucs=3hljn7
```

| Segment | Meaning |
|---|---|
| `Lissabon-LIS-ALIS` | Destination token |
| `/YYYY-MM-DD/YYYY-MM-DD` | Out/return dates |
| `-1,-1` | Unverified meaning — preserve as observed, do not invent one |
| `2` | Traveller count |
| `-1,-1,-1` | Unverified meaning — preserve as observed |
| `CPH` | Origin IATA (trailing segment) |
| `ucs=` | Opaque session token, unverified |

Because two segments are unverified, **prefer the form path** and treat this URL as
observed-not-understood — don't construct it from scratch for a new destination.

### Card fields

A results count reads like `617 resultater`.

Per card, extract: hotel name, city, review score + count, star rating, the `Pakker` label,
board basis (e.g. `Morgenmad`), booking provider (e.g. `Travellink`), one flight line (e.g.
`18:45 København Kastrup, 1 stop`) with its `Se flydetaljer` expander, and alternative offers
under a `Vis alle` expander (e.g. a `Kortere flyrejse` row with its own price and provider).

**Verified: package cards show a bundled total only — there is no per-component flight/hotel
price split.** Do not invent one; state plainly that the price is a bundled total when
presenting a package candidate.

### Price trap (verified — inverted vs. flights)

The headline price on a package card **is the total**, not a per-person figure — the opposite of
the flights vertical. Observed: `12.401 kr.` headline with `6.201 kr. pr. person` beneath. So for
packages: `price` = the headline, `price_per_person` = the `pr. person` line beneath it. Call
this inversion out explicitly whenever presenting flights and packages together, since the
headline maps to a different field in each vertical.

## Normalization

This skill does not define the adapter result record, the normalized candidate record, or
`trip_scraper/seen.json` — `.claude/skills/trip-scraper/SKILL.md` is authoritative for all
three; read it for the full shapes and the dedupe/collapsing rules. Only momondo-specific
mappings are given here:

- `source`: literal `"momondo-search"`.
- `title`: the flight route / hotel name / package hotel name from the card.
- `price`: always the **total** — the `i alt` line for flights, the `Ophold i alt`-switched
  figure for stays, the headline for packages (see each vertical's price trap above).
- `price_per_person`: present wherever the card shows a per-person figure, with the divisor
  stated explicitly (adult count used in the search) — never left implied.
- `currency`: `"DKK"` — what the page reads. Per
  `.claude/skills/holiday-planner/05-budget-rules.md` (EUR primary, DKK noted), also present a
  EUR-converted figure and label it a **conversion estimate** (rate not pinned to a live source),
  on top of the web-read-estimate label below.
- `dates`: `{"depart": "<YYYY-MM-DD>", "return": "<YYYY-MM-DD>"}` for flights and packages;
  `{"check_in": "<YYYY-MM-DD>", "check_out": "<YYYY-MM-DD>"}` for stays. For packages, the
  hotel's own check-in/check-out (if shown separately from the trip dates) is carried in
  `details`, not in `dates`.
- `details`: free-form, per vertical —
  - flights: carriers, stops, layover durations, total duration, fare brand, booking provider,
    baggage note.
  - stays: per-night base price (for reference only — never used to derive `price`), star
    rating, review score/count, distance to city centre, provider, alternative provider prices,
    perks.
  - packages: board basis, booking provider, flight leg summary, hotel check-in/out if shown,
    alternative offers, and an explicit note that the price is a bundled total with no
    component split available.
- `url`: the card's own deep link if present, else the results page URL.

**Overlap with `trivago-search` on stays:** when momondo and trivago surface the same property,
present **both rows separately** with their own price and `source`, visibly linked/marked as the
same underlying property, with the price gap noted as further evidence both are estimates. Score
and rank the property **once**, using the lower of the two prices — see
`.claude/skills/trip-scraper/SKILL.md` for the shared candidate record this relies on.

## Fallback chain

None of these steps may error out a `/scrape` run — always degrade to the next step. Each
vertical (flights, stays, packages) runs and falls back **independently** — a failure on one
never suppresses the others.

Any of these conditions ends the browser attempt for that vertical and drops straight to the
web-search fallback:

1. Extension not connected, or `tabs_context_mcp` shows no usable tab. Checked once per run
   (shared across all three verticals), not once per vertical.
2. Site permission for momondo.dk denied in the extension. Also checked once per run.
3. Bot challenge detected on the loaded page — stop navigating that page immediately.
4. Page unreadable (both `find` and `read_page` fail, or 2-3 consecutive tool failures).
5. Zero results for the given params.

Then, in order, for the affected vertical only:

6. **Fallback: Claude web search** with the same params, normalized into the same result record
   with `source: "momondo-search"` (or a clearly labeled web-search variant if the orchestrating
   skill distinguishes provenance).
7. **Final fallback: ask the user to paste listing text** (a specific flight/hotel/package page,
   email, or screenshot-derived text), per `CLAUDE.md`'s paste-anything fallback and
   `.claude/skills/trip-scraper/SKILL.md`'s "Paste-a-listing fallback" section — this enters the
   same normalize → dedupe → score pipeline as any other candidate, but takes `"source":
   "pasted"`, **not** `"momondo-search"` (per that section; `source` feeds the dedupe key hash).

## Estimate labeling

Every price and availability figure this skill produces is a **web-read estimate, verify at
booking** — never present it as confirmed. momondo is metasearch: its fares routinely exclude
bags, seats, and other fees that the underlying booking site adds later.

## Limits and etiquette

- Read-only navigation of ordinary momondo.dk search-result pages, in the user's own browser
  session, at normal human-paced request volume. No aggressive polling, no scripted request
  volume, no booking, payment, or account-login automation. No cars vertical.
- The DOM structure and the URL grammars above are expected to drift over time, since they were
  captured from a single live session on 2026-07-25 (see point-of-use guidance above for what to
  do when they do).
