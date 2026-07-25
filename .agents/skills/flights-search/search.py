#!/usr/bin/env python3
"""flights-search — Amadeus Self-Service flight-offers search adapter.

Exit codes:
  0 — success (results printed, possibly an empty list)
  2 — no credentials configured (AMADEUS_API_KEY / AMADEUS_API_SECRET unset);
      this is NOT a crash — caller should fall back to Claude web search
  1 — genuine failure (network/HTTP error, bad response, bad arguments)

Never prints or logs the API key/secret, including in error messages.

Normalized result record shape (see SKILL.md for the authoritative doc):
  {
    "source": "flights-search",
    "title": str,
    "url": str | None,
    "price": float,
    "currency": str,
    "price_per_person": float,
    "dates": {"depart": "YYYY-MM-DD", "return": "YYYY-MM-DD" | None},
    "details": {...free-form...}
  }
"""
import argparse
import json
import sys

AMADEUS_TOKEN_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
AMADEUS_OFFERS_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"

NO_CREDENTIALS_EXIT = 2
FAILURE_EXIT = 1


def build_arg_parser():
    p = argparse.ArgumentParser(
        prog="flights-search",
        description=(
            "Search flight offers via the Amadeus Self-Service API. "
            "Requires AMADEUS_API_KEY and AMADEUS_API_SECRET in the environment. "
            "If unset, exits 2 and reports that Claude should fall back to web search."
        ),
    )
    p.add_argument("--origin", help="Origin IATA airport code, e.g. CPH")
    p.add_argument("--destination", help="Destination IATA airport code, e.g. BCN")
    p.add_argument("--depart", help="Departure date, YYYY-MM-DD")
    p.add_argument("--return-date", dest="return_date", default=None, help="Return date, YYYY-MM-DD (omit for one-way)")
    p.add_argument("--adults", type=int, default=1, help="Number of adult travelers (default 1)")
    p.add_argument("--currency", default="EUR", help="Currency code (default EUR)")
    p.add_argument("--max-results", type=int, default=10, help="Maximum number of results (default 10)")
    p.add_argument("--json", action="store_true", help="Print results as a JSON array to stdout")
    return p


def get_credentials():
    import os

    key = os.environ.get("AMADEUS_API_KEY")
    secret = os.environ.get("AMADEUS_API_SECRET")
    if not key or not secret:
        return None
    return key, secret


def no_credentials_response():
    return {
        "status": "no_credentials",
        "message": (
            "AMADEUS_API_KEY and/or AMADEUS_API_SECRET are not set. "
            "Fall back to Claude web search for flight options."
        ),
        "fallback": "web_search",
        "results": [],
    }


def get_access_token(key, secret, requests_mod):
    resp = requests_mod.post(
        AMADEUS_TOKEN_URL,
        data={"grant_type": "client_credentials", "client_id": key, "client_secret": secret},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Amadeus token response did not include an access_token")
    return token


def search_flight_offers(token, args, requests_mod):
    params = {
        "originLocationCode": args.origin,
        "destinationLocationCode": args.destination,
        "departureDate": args.depart,
        "adults": args.adults,
        "currencyCode": args.currency,
        "max": args.max_results,
    }
    if args.return_date:
        params["returnDate"] = args.return_date
    resp = requests_mod.get(
        AMADEUS_OFFERS_URL,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def normalize_offer(offer, currency):
    itineraries = offer.get("itineraries", [])
    depart_date = None
    return_date = None
    if itineraries:
        segments = itineraries[0].get("segments", [])
        if segments:
            depart_date = segments[0].get("departure", {}).get("at", "")[:10]
    if len(itineraries) > 1:
        segments = itineraries[1].get("segments", [])
        if segments:
            return_date = segments[0].get("departure", {}).get("at", "")[:10]

    price_info = offer.get("price", {})
    total = price_info.get("grandTotal") or price_info.get("total")
    try:
        price = float(total) if total is not None else 0.0
    except (TypeError, ValueError):
        price = 0.0

    adults = 1
    try:
        adults = max(1, int(offer.get("travelerPricings", [{}]).__len__() or 1))
    except Exception:
        adults = 1

    return {
        "source": "flights-search",
        "title": f"Flight offer {offer.get('id', '')}".strip(),
        "url": None,
        "price": price,
        "currency": price_info.get("currency", currency),
        "price_per_person": round(price / adults, 2) if adults else price,
        "dates": {"depart": depart_date, "return": return_date},
        "details": {
            "id": offer.get("id"),
            "numberOfBookableSeats": offer.get("numberOfBookableSeats"),
            "itineraries": itineraries,
        },
    }


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # --help/-h is handled by argparse before we get here (exits 0 automatically).

    creds = get_credentials()
    if creds is None:
        payload = no_credentials_response()
        if args.json:
            print(json.dumps(payload))
        else:
            print(payload["message"])
        return NO_CREDENTIALS_EXIT

    # Validate required search args only once we know we can actually search.
    missing = [n for n in ("origin", "destination", "depart") if not getattr(args, n)]
    if missing:
        sys.stderr.write(f"flights-search: missing required arguments: {', '.join(missing)}\n")
        return FAILURE_EXIT

    try:
        import requests
    except ImportError:
        sys.stderr.write("flights-search: the 'requests' package is required (pip install -r requirements.txt)\n")
        return FAILURE_EXIT

    key, secret = creds
    try:
        token = get_access_token(key, secret, requests)
        raw = search_flight_offers(token, args, requests)
    except requests.exceptions.RequestException as exc:
        sys.stderr.write(f"flights-search: network/HTTP error while contacting Amadeus: {exc.__class__.__name__}\n")
        return FAILURE_EXIT
    except Exception as exc:  # noqa: BLE001 - report readable failure, never leak secrets
        sys.stderr.write(f"flights-search: request failed: {exc.__class__.__name__}\n")
        return FAILURE_EXIT

    offers = raw.get("data", []) if isinstance(raw, dict) else []
    results = [normalize_offer(o, args.currency) for o in offers[: args.max_results]]

    if args.json:
        print(json.dumps(results))
    else:
        for r in results:
            print(f"{r['title']}: {r['price']} {r['currency']} ({r['dates']['depart']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
