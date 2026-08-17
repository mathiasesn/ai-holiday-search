# 04 — Itinerary Templates and Pacing Rules

> Pacing rules here are enforced, not suggested. `/plan`'s verification step (README step 6)
> rejects any draft itinerary that breaks them and sends it back for revision. Limits below
> are sensible defaults; `/setup` may tighten or loosen them in your `<DATA_ROOT>/profile/` copy based on
> `02-travel-style.md`. If a filled copy exists in `<DATA_ROOT>/profile/`, it wins.

## Pacing rules (defaults — enforced by /plan)

- **Max anchor activities per day:** 2 (one major sight/activity block in the morning, one in
  the afternoon). With young kids in the group (per `01-traveler-profile.md`), **max 1** anchor
  activity per day.
- **Unplanned/rest days:** at least 1 day with nothing scheduled per 5 nights of the trip.
- **Max transit between consecutive activities:** ~30 minutes of travel time between the end of
  one activity and the start of the next, unless the transit itself is the activity (e.g. a
  scenic train).
- **Max single travel-day transfer time:** arrival/departure days should not schedule anchor
  activities if door-to-door travel that day exceeds ~4 hours.
- **No back-to-back early starts:** at most one activity per day requiring departure before
  9:00, unless the traveler's style profile explicitly allows it.

These are examples of the *shape* of the rule; the numeric limits are what `/setup` should tune
per traveler (e.g. a childfree, fast-paced couple might raise "max anchor activities" to 3).

## Day-plan output template

```markdown
### Day <N> — <Weekday>, <Date> — <Day theme, e.g. "Old Town & Harbor">

**Morning**
- <Anchor activity 1> (<opening hours>, <est. duration>) — <one-line why it fits>

**Transit:** <mode>, ~<minutes> min

**Afternoon**
- <Anchor activity 2, omit if young kids in group> (<opening hours>, <est. duration>)

**Evening**
- <Dinner suggestion or free time>

**Notes:** <weather note, booking-ahead note, or "unplanned day" if applicable>
```

## Trip-level output template

```markdown
# <Destination> — <N> nights, <date range>

**Fit score:** <score>/100 (<band>) — see reasoning below
**Travelers:** <adults, kids/ages from profile>
**Home airport:** <airport>

## Fit reasoning
<criterion-by-criterion reasoning from 03-trip-evaluation.md>

## Itinerary
<Day-plan blocks, one per day, using the template above>

## Budget
<Budget table from 05-budget-rules.md>

## Verification checklist
- [ ] Budget rows sum correctly
- [ ] No day exceeds pacing rules (max anchors/day, transit limits, rest-day ratio)
- [ ] Every named venue confirmed to exist via search
- [ ] Travel legs between activities are feasible within transit limits
- [ ] Reviewer feedback incorporated

## Booking to-do list
- [ ] <Flights>
- [ ] <Accommodation>
- [ ] <Pre-bookable activities/tickets>
```

Output is **Markdown only** — never generate or reference a PDF.

---

Used by: `/plan` (steps 3–7: draft, review, revise, verify, present).
