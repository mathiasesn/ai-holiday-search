# 05 — Budget Rules

> This is a generic tracked template; defaults below apply until `/setup` writes a filled
> `<DATA_ROOT>/profile/05-budget-rules.md` copy. If a filled copy exists in `<DATA_ROOT>/profile/`, it wins.

## Cost categories

Every itinerary budget table must break costs into these categories:

| Category         | How to verify                                                                 |
| ------------------ | -------------------------------------------------------------------------------- |
| Transport (flights/trains) | Web-search or adapter-search current fares for the actual dates; note if price is estimated vs. quoted |
| Stay                 | Nightly rate × nights from a real listing or comparable web-search result |
| Activities            | Sum of ticket/tour prices for every named anchor activity, from official sites where possible |
| Food                  | Per-person daily estimate based on destination cost-of-living and food-priority level in `02-travel-style.md` |
| Local transport         | Public transit passes, taxis/rideshare, airport transfers |
| Buffer                 | Required — see below |

## Required buffer

- **Minimum buffer: 10% of the subtotal** (transport + stay + activities + food + local
  transport), added as its own line item — never silently folded into another category.
- Increase to 15% for trips with more than one uncertain/estimated cost category, or for
  destinations with volatile pricing (peak season, currency swings).

## Per-person vs. total

- State clearly, for every line, whether the figure is **per person** or **total for the group**.
- The trip-level total budget must always show both a per-person and a group total figure.

## Currency handling

- **Primary currency: EUR.** Convert and note the equivalent in **DKK** alongside it when the
  traveler's home currency is DKK (per `01-traveler-profile.md`), e.g. `€1,050 (~7,830 DKK)`.
- Use the exchange rate at the time of the estimate and note that it is indicative, not locked.
- If a source quotes a different currency (e.g. a local operator quoting the destination's
  currency), convert to EUR for the budget table and keep the original figure in parentheses.

## Estimates must be labelled

Every cost that is not a confirmed booking price must be explicitly labelled as an estimate,
e.g. `€45/night (web-search estimate, verify at booking)`. Never present a searched or inferred
price as a confirmed fact.

## Example budget table

```markdown
| Category        | Per person | Total (2 adults) | Notes                          |
| ---------------- | ---------: | ----------------: | -------------------------------- |
| Flights (CPH–OPO) | €180       | €360               | quoted fare, booked dates        |
| Stay (5 nights)   | €225       | €450               | estimate, apartment listing      |
| Activities        | €60        | €120               | 2 confirmed ticket prices        |
| Food              | €175       | €350               | estimate, €35/day per person     |
| Local transport    | €25        | €50                | metro pass, estimate             |
| **Subtotal**      | **€665**   | **€1,330**         |                                   |
| Buffer (10%)      | €67        | €133               | required                         |
| **Total**         | **€732**   | **€1,463**         | ≈ 5,460 DKK per person            |
```

---

Used by: `/plan` (step 3 draft budget, step 6 verification that rows sum correctly).
