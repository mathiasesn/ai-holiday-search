# Search Queries — Default Settings for /scrape

> This is a generic tracked template. `/setup` writes your filled-in personal copy to
> `profile/search-queries.md` (gitignored). If that file exists, **it wins** — read it
> instead of this one. Values below are illustrative European examples only, not defaults you
> must keep.

## Default destination list

<!-- FILL IN: destinations you'd consider without being asked -->
- Porto, Portugal
- Ljubljana, Slovenia
- Split, Croatia
- Valencia, Spain
- Athens, Greece

## Default date windows

<!-- FILL IN: recurring windows you search by default -->
- Any 5–7 night window in the last two weeks of October
- School holiday weeks (adjust per local calendar)

## Price ceiling

<!-- FILL IN -->
- Max €1,500 per person, all-in (flights + stay + est. activities/food)

## Max flight time

<!-- FILL IN -->
- Max 5 hours one-way from home airport(s) (see `01-traveler-profile.md`)

## Sources to query

<!-- FILL IN: enable/disable per source availability -->
| Source           | Query by default? |
| ----------------- | ------------------ |
| flights-search     | yes                 |
| stays-search        | yes                 |
| packages-search     | yes, if configured for your local operators |
| trivago-search      | yes (needs an attended browser session; else degrades to web search) |

## Home airport(s)

<!-- FILL IN, mirrors 01-traveler-profile.md for convenience -->
- CPH (Copenhagen), BLL (Billund) — examples, replace with your own

---

Referenced by the README's Customization table: "Default destinations, date windows, and
sources for /scrape." Used by `trip-scraper/SKILL.md` to build adapter queries.
