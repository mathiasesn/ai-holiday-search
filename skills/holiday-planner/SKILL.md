---
name: holiday-planner
description: Core holiday-planning skill. Use it to build and hold a traveler's profile and travel style, score candidate trips for fit, draft and verify day-by-day itineraries with pacing and budget rules, and produce packing/prep checklists. Invoked by /setup, /scrape, /plan, and /watch whenever they need the traveler's preferences, the fit-scoring framework, itinerary structure, budget rules, or packing guidance.
---

# Holiday Planner

The core, destination-agnostic planning skill for ai-holiday-search. It defines who the
traveler is, how a candidate trip is scored for fit, how day-by-day itineraries are
structured and paced, how budgets are verified, and how packing/prep checklists are built.

## What this skill does

- Holds the structure of the traveler's profile and travel style (filled in by `/setup`).
- Defines the fit-scoring framework used by `/scrape` to rank candidate trips and by `/plan`
  to honestly assess a specific trip before drafting it.
- Defines itinerary structure and hard pacing rules, enforced by `/plan`'s verification step.
- Defines budget categories, verification rules, and the required buffer.
- Defines packing lists and pre-departure checklists.

## When to invoke this skill

- `/setup` — to know what fields the traveler profile and travel style need, and to write the
  filled personal copies to `<DATA_ROOT>/profile/`.
- `/scrape` — to score and rank candidate trips against the traveler's profile and style.
- `/plan` — to evaluate fit, draft the itinerary, enforce pacing rules, verify the budget, and
  generate a packing list.
- `/watch` — to re-derive a trip's identity (route, dates) when checking for price changes.

## How the reference files work

Each of the six numbered files below is a **generic tracked template** with real structure and
`<!-- FILL IN -->` markers. `/setup` writes the traveler's filled-in personal copy to
`<DATA_ROOT>/profile/<same-filename>`. **When a filled copy exists in `<DATA_ROOT>/profile/`, it always
wins over the template here** — read `<DATA_ROOT>/profile/` first and fall back to these templates only if
`<DATA_ROOT>/profile/` is empty or missing.

## Reference index

1. [Traveler profile](01-traveler-profile.md) — who travels, home airport(s), budget, dates, visas.
2. [Travel style](02-travel-style.md) — beach/city/nature/ski, pace, standards, dealbreakers.
3. [Trip evaluation](03-trip-evaluation.md) — the weighted fit-scoring framework (0-100 scale).
4. [Itinerary templates](04-itinerary-templates.md) — day-plan structure and pacing rules.
5. [Budget rules](05-budget-rules.md) — cost categories, buffer, currency handling.
6. [Packing and prep](06-packing-and-prep.md) — packing lists, documents, insurance, timeline.
