# documents/

Source material for `/setup`. Everything in this folder (except this README and the
`.gitkeep` placeholders) is gitignored — it stays on your machine only.

## Layout

```
documents/
├── README.md          # this file (tracked)
├── past-trips/         # old itineraries, booking confirmations, trip notes
└── preferences/        # freeform notes on likes/dislikes, style, dealbreakers
```

### `past-trips/`

Drop in anything that documents where you've actually traveled:

- Past itineraries (Markdown, PDF, plain text — `/setup` reads what it can)
- Booking confirmations or trip summaries
- Photos are not needed; a short "what we did" note is more useful than a receipt

### `preferences/`

Freeform notes about your travel style:

- "Trips we loved / trips we hated" and why
- Dealbreakers and must-haves (e.g. "no hostels", "must be walkable", "direct flights only")
- Pace preferences, food priorities, accommodation standard

## How it's used

Run `/setup` and choose the "documents folder" mode. Claude reads everything here and
builds your traveler profile in the (gitignored) `profile/` folder. This mode is
idempotent — safe to re-run any time you add more material.

If this folder is empty, `/setup` falls back to a pasted freeform description or an
interactive interview instead.

## Privacy

Nothing in `past-trips/` or `preferences/` is ever committed to git — see the repo's
`.gitignore`. Only this README and two `.gitkeep` placeholders (keeping the empty folders
visible in a fresh clone) are tracked.
