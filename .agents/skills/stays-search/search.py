#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""stays-search — accommodation search adapter (public API/feed + web-search fallback).

This adapter is stdlib + requests only. It is shipped without a bundled paid API
key (most hotel/rental APIs require a commercial partnership), so out of the box
it always reports the documented "use Claude web search + paste-a-listing" fallback.
If you have access to a public stays API or feed (e.g. a national tourism board
open-data feed), wire it into `fetch_stays()` below; the CLI shape and normalized
output stay the same either way.

Exit codes:
  0 — success (results printed, possibly an empty list)
  2 — no source configured (no STAYS_API_URL/STAYS_API_KEY, or feed unreachable by
      design); this is NOT a crash — caller should fall back to Claude web search
  1 — genuine failure (network/HTTP error against a configured source, bad arguments)

Never prints or logs secrets (e.g. STAYS_API_KEY), including in error messages.

Result record: source, title, url, price, currency, price_per_person, dates
(check_in/check_out), details (free-form). Authoritative shape:
skills/trip-scraper/SKILL.md ("Adapter result record").
"""
import argparse
import json
import os
import sys

NO_CREDENTIALS_EXIT = 2
FAILURE_EXIT = 1


def build_arg_parser():
    p = argparse.ArgumentParser(
        prog="stays-search",
        description=(
            "Search accommodation (hotels/rentals) via a configured public API/feed. "
            "Requires STAYS_API_URL (and optionally STAYS_API_KEY) in the environment. "
            "If unset, exits 2 and reports that Claude should fall back to web search "
            "+ paste-a-listing."
        ),
    )
    p.add_argument("--destination", help="Destination name or city, e.g. Lisbon")
    p.add_argument("--check-in", dest="check_in", help="Check-in date, YYYY-MM-DD")
    p.add_argument("--check-out", dest="check_out", help="Check-out date, YYYY-MM-DD")
    p.add_argument("--guests", type=int, default=2, help="Number of guests (default 2)")
    p.add_argument("--currency", default="EUR", help="Currency code (default EUR)")
    p.add_argument("--max-results", type=int, default=10, help="Maximum number of results (default 10)")
    p.add_argument("--json", action="store_true", help="Print results as a JSON array to stdout")
    return p


def get_source_config():
    """Return (api_url, api_key_or_None) if a stays source is configured, else None.

    api_key is optional (some open feeds need none); api_url is required.
    """
    api_url = os.environ.get("STAYS_API_URL")
    if not api_url:
        return None
    api_key = os.environ.get("STAYS_API_KEY")
    return api_url, api_key


def no_source_response():
    return {
        "status": "no_credentials",
        "reason": "no_source_configured",
        "message": (
            "No stays source is configured (STAYS_API_URL is not set). "
            "Fall back to Claude web search + paste-a-listing for accommodation."
        ),
        "fallback": "web_search",
        "results": [],
    }


def fetch_stays(api_url, api_key, args, requests_mod):
    """Query the configured stays API/feed and return its raw parsed JSON payload.

    Fork this function to point at your own stays feed/API. The request shape below
    is a generic placeholder (query params); adapt as needed for your source.
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    params = {
        "destination": args.destination,
        "check_in": args.check_in,
        "check_out": args.check_out,
        "guests": args.guests,
        "currency": args.currency,
        "limit": args.max_results,
    }
    resp = requests_mod.get(api_url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize_stay(item, currency, check_in, check_out):
    price = item.get("price", 0.0)
    try:
        price = float(price)
    except (TypeError, ValueError):
        price = 0.0
    guests = item.get("guests") or 1
    try:
        guests = max(1, int(guests))
    except (TypeError, ValueError):
        guests = 1
    return {
        "source": "stays-search",
        "title": item.get("title") or item.get("name") or "Untitled stay",
        "url": item.get("url"),
        "price": price,
        "currency": item.get("currency", currency),
        "price_per_person": round(price / guests, 2) if guests else price,
        "dates": {"check_in": item.get("check_in", check_in), "check_out": item.get("check_out", check_out)},
        "details": {k: v for k, v in item.items() if k not in {"title", "name", "url", "price", "currency"}},
    }


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    config = get_source_config()
    if config is None:
        payload = no_source_response()
        if args.json:
            print(json.dumps(payload))
        else:
            print(payload["message"])
        return NO_CREDENTIALS_EXIT

    missing = [n for n in ("destination", "check_in", "check_out") if not getattr(args, n)]
    if missing:
        sys.stderr.write(f"stays-search: missing required arguments: {', '.join(missing)}\n")
        return FAILURE_EXIT

    try:
        import requests
    except ImportError:
        sys.stderr.write("stays-search: the 'requests' package is required (run via 'uv run search.py', which installs it automatically)\n")
        return FAILURE_EXIT

    api_url, api_key = config
    try:
        raw = fetch_stays(api_url, api_key, args, requests)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"stays-search: request failed: {exc.__class__.__name__}\n")
        return FAILURE_EXIT

    items = raw.get("results", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    results = [normalize_stay(i, args.currency, args.check_in, args.check_out) for i in items[: args.max_results]]

    if args.json:
        print(json.dumps(results))
    else:
        for r in results:
            print(f"{r['title']}: {r['price']} {r['currency']} ({r['dates']['check_in']} - {r['dates']['check_out']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
