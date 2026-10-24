"""Nearby Toyota dealers (FR-035) behind an interface.

Candidates come from SerpApi's Google Maps engine and are ranked here by straight-line distance from
the customer, because Maps orders by relevance: in the captured response the closest dealer came back
fourth. The parser was written from that captured response (`tests/fixtures/serpapi_maps_toyota.json`),
which shows what is and is not in it:
  * a result's `type` is "Toyota dealer" for a dealership; service departments, parts stores, used-car
    departments and the corporate campus come back too and are dropped;
  * the fields used are `title`, `address`, `hours`, `rating` and `gps_coordinates`;
  * `hours` has a narrow no-break space (U+202F) before AM and PM, which is turned into a plain space.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Protocol

import httpx

EARTH_RADIUS_MILES = 3958.8
SERPAPI_URL = "https://serpapi.com/search.json"
_DEALER_TYPE = "toyota dealer"


class DealerLookupError(Exception):
    """The dealer search could not be completed. The message is safe to show: it never carries a URL
    or a key, because an httpx error message contains the full request URL, API key included."""


@dataclass(frozen=True)
class Dealer:
    name: str
    address: str
    hours: str | None
    rating: float | None
    lat: float
    lng: float
    distance_miles: float | None = None


class DealersClient(Protocol):
    def search(self, zip_code: str, lat: float, lng: float) -> list[Dealer]:
        """Candidate dealers near the location, in any order."""
        ...


def _plain(text: str | None) -> str | None:
    if not text:
        return None
    return text.replace(" ", " ").replace(" ", " ").strip() or None


def parse_maps_results(payload: dict) -> list[Dealer]:
    """The dealerships in a Google Maps search response, in the order returned."""
    error = payload.get("error")
    if error:
        if "hasn't returned any results" in str(error):
            return []  # SerpApi reports an empty search as an error
        raise DealerLookupError("The dealer search returned an error.")
    dealers = []
    for r in payload.get("local_results", []):
        if str(r.get("type", "")).lower() != _DEALER_TYPE:
            continue
        gps = r.get("gps_coordinates") or {}
        if not r.get("title") or not r.get("address") or "latitude" not in gps or "longitude" not in gps:
            continue
        rating = r.get("rating")
        dealers.append(
            Dealer(
                name=r["title"],
                address=r["address"],
                hours=_plain(r.get("hours")),
                rating=float(rating) if rating is not None else None,
                lat=float(gps["latitude"]),
                lng=float(gps["longitude"]),
            )
        )
    return dealers


class SerpApiDealers:
    """Toyota dealers near a point, from the Google Maps engine."""

    def __init__(self, api_key: str, http: httpx.Client | None = None):
        if not api_key:
            raise ValueError("SERPAPI_API_KEY is required")
        self._key = api_key
        self._http = http or httpx.Client(timeout=20)

    def search(self, zip_code: str, lat: float, lng: float) -> list[Dealer]:
        params = {
            "engine": "google_maps",
            "q": "Toyota dealer",
            "ll": f"@{lat},{lng},12z",
            "type": "search",
            "hl": "en",
            "api_key": self._key,
        }
        try:
            response = self._http.get(SERPAPI_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            # Deliberately not chained: the original error text includes the request URL and the key.
            raise DealerLookupError("The dealer search could not be reached.") from None
        return parse_maps_results(payload)


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def nearest(dealers: list[Dealer], lat: float, lng: float, n: int = 3) -> list[Dealer]:
    """The `n` closest dealers, nearest first, each with its distance filled in."""
    ranked = sorted(
        (replace(d, distance_miles=round(haversine_miles(lat, lng, d.lat, d.lng), 1)) for d in dealers),
        key=lambda d: d.distance_miles,
    )
    return ranked[:n]


class FakeDealers:
    """A stand-in with a hand-written list around Plano, TX (not real businesses). Tests that need
    realistic data build one from the captured response with `parse_maps_results`."""

    def __init__(self, dealers: list[Dealer] | None = None):
        self._dealers = dealers if dealers is not None else [
            Dealer("Example Toyota North", "100 Example Pkwy, Plano, TX", "Open · Closes 8 PM", 4.6, 33.10, -96.83),
            Dealer("Example Toyota Central", "200 Sample Ave, Dallas, TX", "Open · Closes 7 PM", 4.4, 32.78, -96.80),
            Dealer("Example Toyota East", "300 Test Blvd, Garland, TX", "Closed · Opens 9 AM", 4.2, 32.91, -96.64),
            Dealer("Example Toyota West", "400 Demo St, Irving, TX", "Open · Closes 6 PM", 4.7, 32.81, -96.95),
            Dealer("Example Toyota South", "500 Mock Rd, Waxahachie, TX", None, None, 32.39, -96.85),
        ]
        self.calls = 0

    def search(self, zip_code: str, lat: float, lng: float) -> list[Dealer]:
        self.calls += 1
        return list(self._dealers)
