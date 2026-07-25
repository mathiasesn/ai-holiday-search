# 03 — Trip Evaluation (Fit Scoring)

> This file's framework is operational, not decorative — `/scrape` and `/plan` must actually
> compute scores this way, not just gesture at "fit." Weights below are generic sensible
> defaults; `/setup` may adjust them in your `profile/03-trip-evaluation.md` copy per the
> Customization table in the README. If a filled copy exists in `profile/`, it wins.

## Scoring criteria and weights

Each candidate trip is scored 0-100 as a weighted sum of five named criteria. Default weights
(customize in your profile copy, they must sum to 100):

| Criterion            | Weight | What it measures                                                              |
| --------------------- | ------ | ------------------------------------------------------------------------------ |
| Style match            | 30     | How well the destination/activities match `02-travel-style.md` (trip type, pace, standard) |
| Budget fit              | 25     | How the total estimated cost compares to the budget range in `01-traveler-profile.md` |
| Travel time             | 20     | Flight/transfer time against the max travel time in `01-traveler-profile.md` |
| Season/weather fit      | 15     | Expected weather for the travel dates against the trip type (e.g. beach trip needs warm, dry weather) |
| Group suitability       | 10     | Fit for the specific group — kids' ages, mobility constraints, pace tolerance |

Each criterion is scored 0-100 individually, then combined:

```
total_score = 0.30*style + 0.25*budget + 0.20*travel_time + 0.15*season + 0.10*group
```

## The 0-100 scale

| Band    | Meaning                                                                  |
| ------- | ------------------------------------------------------------------------- |
| 85-100  | Excellent fit. Matches profile closely on every criterion, no compromises. |
| 70-84   | Good fit. Strong match with one or two minor compromises (e.g. slightly over budget, a longer layover). |
| 50-69   | Workable. Meets the basics but has real trade-offs worth flagging clearly. |
| 30-49   | Poor fit. Multiple significant mismatches; only worth showing if nothing better exists. |
| 0-29    | Bad fit. Do not recommend; show only if the user explicitly asks to see everything. |

## Hard rule: dealbreakers override the score

Before computing the weighted score, check every dealbreaker in `02-travel-style.md`. If the
trip violates **any** dealbreaker (e.g. requires an overnight layover when "no overnight
layovers" is a dealbreaker):

- **Cap the total score at 25**, regardless of how well it scores on every other criterion, OR
- **Disqualify it entirely** (score = 0, excluded from results) if the dealbreaker is safety-
  or accessibility-related (e.g. no accessible room for a mobility constraint).

This means **a cheap trip that violates a dealbreaker must rank below a pricier trip that fits**,
even if the cheap trip would otherwise score higher on budget and style. Never let a high raw
weighted score override a dealbreaker violation.

## Reasoning must always be shown

Every score presented to the user must be accompanied by a one-line reason per criterion, e.g.:

```
Porto, 5 nights, 14–19 Oct — Score: 78/100 (Good fit)
  Style match:     85  — walkable old town, food-forward, matches "city + food" preference
  Budget fit:       70  — €1,050/person vs €800–1,500 range, mid-range
  Travel time:      90  — 3h10m direct flight from CPH, well under 5h max
  Season fit:        75  — mid-teens and mild rain in October, acceptable for a city trip
  Group suitability: 70  — flat old-town cobblestones, note for stroller use
  Dealbreakers: none violated
```

## Worked example

Inputs: style=85, budget=70, travel_time=90, season=75, group=70, no dealbreakers violated.

```
total = 0.30*85 + 0.25*70 + 0.20*90 + 0.15*75 + 0.10*70
      = 25.5 + 17.5 + 18 + 11.25 + 7
      = 79.25 → 79/100 → "Good fit"
```

If this same trip required an overnight layover and "no overnight layovers" is a dealbreaker,
the score is capped at 25/100 ("Bad fit") regardless of the 79.25 raw weighted score.

---

Used by: `/scrape` (ranks all candidates by this score), `/plan` (step 2, honest fit
assessment before drafting effort is spent).
