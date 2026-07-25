#!/usr/bin/env python3
"""packages-search — WORKING TEMPLATE for package/charter holiday operators.

This is a fork-and-fill template, not a live integration: no package operator
ships by default (most charter operators require a commercial API agreement),
so out of the box this CLI runs cleanly and reports that no operator is
configured. To wire up a real operator:

  1. Set PACKAGES_API_URL (and PACKAGES_API_KEY if your operator needs one) in
     your local environment (never commit real values).
  2. Edit `fetch_packages()` below to call your operator's actual endpoint
     (method, auth scheme, query params) instead of the generic GET placeholder.
  3. Edit `parse_results(payload) -> list[dict]` below — THIS IS THE SEAM.
     It takes whatever your operator's API returns (already JSON-decoded) and
     must return a list of dicts, each with at least: title, url, price,
     currency, dates (dict with e.g. depart/return or check_in/check_out),
     and any operator-specific fields (hotel name, board basis, transfer
     included, etc.). Nothing else in this file needs to change.
  4. Update this SKILL.md sibling file to describe your operator, its
     credentials, and coverage.

Exit codes:
  0 — success (results printed, possibly an empty list)
  2 — no operator configured (PACKAGES_API_URL unset); this is NOT a crash —
      caller should fall back to Claude web search
  1 — genuine failure (network/HTTP error against a configured operator, bad
      arguments, or parse_results() raising on unexpected payload shape)

Never prints or logs secrets (e.g. PACKAGES_API_KEY), including in error
messages.

Result record: source, title, url, price, currency, price_per_person, dates
(depart/return), details (free-form, operator-specific). Authoritative shape:
.claude/skills/trip-scraper/SKILL.md ("Adapter result record").
"""
import argparse
import json
import os
import sys

NO_CREDENTIALS_EXIT = 2
FAILURE_EXIT = 1


def build_arg_parser():
    p = argparse.ArgumentParser(
        prog="packages-search",
        description=(
            "Search package/charter holidays via a configured operator API. "
            "This is a fork-and-fill template: no operator is bundled by default. "
            "Set PACKAGES_API_URL (and PACKAGES_API_KEY if required) to enable it; "
            "until then this exits 2 and reports that Claude should fall back to "
            "web search."
        ),
    )
    p.add_argument("--destination", help="Destination name, e.g. Antalya")
    p.add_argument("--depart-airport", dest="depart_airport", help="Home airport IATA code, e.g. CPH")
    p.add_argument("--depart", help="Departure date, YYYY-MM-DD")
    p.add_argument("--return-date", dest="return_date", default=None, help="Return date, YYYY-MM-DD")
    p.add_argument("--adults", type=int, default=2, help="Number of adult travelers (default 2)")
    p.add_argument("--currency", default="EUR", help="Currency code (default EUR)")
    p.add_argument("--max-results", type=int, default=10, help="Maximum number of results (default 10)")
    p.add_argument("--json", action="store_true", help="Print results as a JSON array to stdout")
    return p


def get_operator_config():
    """Return (api_url, api_key_or_None) if an operator is configured, else None."""
    api_url = os.environ.get("PACKAGES_API_URL")
    if not api_url:
        return None
    return api_url, os.environ.get("PACKAGES_API_KEY")


def no_operator_response():
    return {
        "status": "no_credentials",
        "reason": "no_operator_configured",
        "message": (
            "No package/charter operator is configured (PACKAGES_API_URL is not set). "
            "This is a template skill — fork it for your local operator, or fall back "
            "to Claude web search + paste-a-listing for package holidays."
        ),
        "fallback": "web_search",
        "results": [],
    }


def fetch_packages(api_url, api_key, args, requests_mod):
    """CHANGE ME: call your operator's real endpoint here.

    The GET + query-params shape below is a generic placeholder. Replace it with
    whatever your operator actually requires (POST body, different auth header,
    pagination, etc.). Must return the operator's JSON-decoded response payload —
    parse_results() below is what turns that into normalized records.
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    params = {
        "destination": args.destination,
        "departure_airport": args.depart_airport,
        "depart_date": args.depart,
        "return_date": args.return_date,
        "adults": args.adults,
        "currency": args.currency,
        "limit": args.max_results,
    }
    resp = requests_mod.get(api_url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_results(payload):
    """THE SEAM: turn your operator's raw JSON payload into a list of dicts.

    Fork target. `payload` is whatever fetch_packages() returned (already
    JSON-decoded — a dict or list, depending on your operator). Return a plain
    list of dicts; normalize_package() below will fill in any missing
    normalized-shape fields with safe defaults, so you only need to extract
    what your operator actually gives you.

    The placeholder implementation below assumes a payload shaped like
    {"packages": [{"name": ..., "price": ..., "currency": ..., "url": ...,
    "depart_date": ..., "return_date": ...}, ...]} — replace entirely to match
    your real operator's response shape.
    """
    items = payload.get("packages", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("packages-search: parse_results() expected a list of package items")
    return items


def normalize_package(item, currency, adults):
    price = item.get("price", 0.0)
    try:
        price = float(price)
    except (TypeError, ValueError):
        price = 0.0
    people = adults if adults else 1
    return {
        "source": "packages-search",
        "title": item.get("name") or item.get("title") or "Untitled package",
        "url": item.get("url"),
        "price": price,
        "currency": item.get("currency", currency),
        "price_per_person": round(price / people, 2) if people else price,
        "dates": {
            "depart": item.get("depart_date"),
            "return": item.get("return_date"),
        },
        "details": {
            k: v
            for k, v in item.items()
            if k not in {"name", "title", "url", "price", "currency", "depart_date", "return_date"}
        },
    }


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    config = get_operator_config()
    if config is None:
        payload = no_operator_response()
        if args.json:
            print(json.dumps(payload))
        else:
            print(payload["message"])
        return NO_CREDENTIALS_EXIT

    missing = [n for n in ("destination", "depart") if not getattr(args, n)]
    if missing:
        sys.stderr.write(f"packages-search: missing required arguments: {', '.join(missing)}\n")
        return FAILURE_EXIT

    try:
        import requests
    except ImportError:
        sys.stderr.write("packages-search: the 'requests' package is required (pip install -r requirements.txt)\n")
        return FAILURE_EXIT

    api_url, api_key = config
    try:
        raw = fetch_packages(api_url, api_key, args, requests)
        items = parse_results(raw)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"packages-search: request failed: {exc.__class__.__name__}\n")
        return FAILURE_EXIT

    results = [normalize_package(i, args.currency, args.adults) for i in items[: args.max_results]]

    if args.json:
        print(json.dumps(results))
    else:
        for r in results:
            print(f"{r['title']}: {r['price']} {r['currency']} ({r['dates']['depart']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
