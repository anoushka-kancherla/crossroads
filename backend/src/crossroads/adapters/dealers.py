"""Nearby Toyota dealers (FR-035) behind an interface.

Ranking is by straight-line distance from the customer's coordinates. The real SerpApi Google Maps
client is task T054 and is built from a captured response (T053), not from guessed field names; until
then the fake below returns a hand-written PROVISIONAL list.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Protocol

EARTH_RADIUS_MILES = 3958.8


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
    """Hand-written, provisional candidates around Plano, TX. Not real businesses."""

    def __init__(self, dealers: list[Dealer] | None = None):
        self._dealers = dealers if dealers is not None else [
            Dealer("Example Toyota North", "100 Example Pkwy, Plano, TX", "Open · Closes 8 PM", 4.6, 33.10, -96.83),
            Dealer("Example Toyota Central", "200 Sample Ave, Dallas, TX", "Open · Closes 7 PM", 4.4, 32.78, -96.80),
            Dealer("Example Toyota East", "300 Test Blvd, Garland, TX", "Closed · Opens 9 AM", 4.2, 32.91, -96.64),
            Dealer("Example Toyota West", "400 Demo St, Irving, TX", "Open · Closes 6 PM", 4.7, 32.81, -96.95),
            Dealer("Example Toyota South", "500 Mock Rd, Waxahachie, TX", None, None, 32.39, -96.85),
        ]

    def search(self, zip_code: str, lat: float, lng: float) -> list[Dealer]:
        return list(self._dealers)
