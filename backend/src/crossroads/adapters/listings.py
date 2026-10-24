"""Used-car listing prices (FR-005), best effort, behind an interface.

SerpApi has no used-car listings engine that I know of, so the real client reads dollar amounts
out of Google search results for the car and keeps the median when it finds enough plausible ones.
When it finds too few, or the call fails, the caller falls back to the depreciation estimate (FR-005),
so nothing depends on this working. Unverified against a live key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import httpx

SERPAPI_URL = "https://serpapi.com/search.json"
_PRICE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d{4,6})")
MIN_PRICE, MAX_PRICE = Decimal(3_000), Decimal(150_000)


@dataclass(frozen=True)
class ListingQuote:
    low: Decimal
    median: Decimal
    high: Decimal
    n: int


class ListingsClient(Protocol):
    def lookup(self, make: str, model: str, year: int, zip_code: str) -> ListingQuote | None: ...


def prices_from_results(payload: dict) -> list[Decimal]:
    """Plausible dollar amounts found in the titles and snippets of organic results."""
    found: list[Decimal] = []
    for item in payload.get("organic_results", []):
        text = f"{item.get('title', '')} {item.get('snippet', '')}"
        for raw in _PRICE.findall(text):
            price = Decimal(raw.replace(",", ""))
            if MIN_PRICE <= price <= MAX_PRICE:
                found.append(price)
    return found


def quote_from_prices(prices: list[Decimal], min_n: int = 3) -> ListingQuote | None:
    if len(prices) < min_n:
        return None
    s = sorted(prices)
    mid = len(s) // 2
    median = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
    return ListingQuote(low=s[0], median=median, high=s[-1], n=len(s))


class SerpApiListings:
    def __init__(self, api_key: str, http: httpx.Client | None = None):
        if not api_key:
            raise ValueError("SERPAPI_API_KEY is required")
        self._key = api_key
        self._http = http or httpx.Client(timeout=15)

    def lookup(self, make: str, model: str, year: int, zip_code: str) -> ListingQuote | None:
        r = self._http.get(
            SERPAPI_URL,
            params={"engine": "google", "q": f"{year} {make} {model} for sale near {zip_code}",
                    "api_key": self._key},
        )
        r.raise_for_status()
        return quote_from_prices(prices_from_results(r.json()))


class FakeListings:
    def __init__(self, quotes: dict[tuple[str, str, int, str], ListingQuote] | None = None):
        self._quotes = quotes or {}

    def lookup(self, make: str, model: str, year: int, zip_code: str) -> ListingQuote | None:
        return self._quotes.get((make, model, year, zip_code))
