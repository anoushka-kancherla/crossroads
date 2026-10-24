"""Listings adapter: price extraction, median, and the fake. No network."""

from decimal import Decimal as D

import httpx
import pytest

from crossroads.adapters.listings import (
    FakeListings,
    ListingQuote,
    SerpApiListings,
    prices_from_results,
    quote_from_prices,
)

# Hand-written, in the shape SerpApi's Google results use. Not a captured response.
SAMPLE = {
    "organic_results": [
        {"title": "2023 Toyota RAV4 XLE for sale", "snippet": "Great price $22,500 with low miles"},
        {"title": "Used RAV4 - $23,900", "snippet": "Certified, 12,000 miles"},
        {"title": "RAV4 deals", "snippet": "From $21,750 or $399 per month"},
        {"title": "Parts", "snippet": "Brake pads $89 and a $1,000,000 dream"},
    ]
}


def test_plausible_prices_are_extracted_and_noise_is_dropped():
    assert prices_from_results(SAMPLE) == [D(22500), D(23900), D(21750)]


def test_quote_is_low_median_high():
    q = quote_from_prices([D(22500), D(23900), D(21750)])
    assert q == ListingQuote(low=D(21750), median=D(22500), high=D(23900), n=3)


def test_median_of_an_even_count_is_the_midpoint():
    assert quote_from_prices([D(20000), D(22000), D(24000), D(26000)]).median == D(23000)


def test_too_few_prices_gives_no_quote_so_the_caller_falls_back():
    assert quote_from_prices([D(22500), D(23900)]) is None
    assert quote_from_prices([]) is None


def test_the_serpapi_client_returns_a_quote_from_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["api_key"] == "KEY"
        assert "RAV4" in request.url.params["q"] and "75024" in request.url.params["q"]
        return httpx.Response(200, json=SAMPLE)

    client = SerpApiListings("KEY", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.lookup("Toyota", "RAV4", 2023, "75024").median == D(22500)


def test_the_serpapi_client_needs_a_key():
    with pytest.raises(ValueError):
        SerpApiListings("")


def test_the_fake_returns_what_it_was_given_and_none_otherwise():
    q = ListingQuote(D(1), D(2), D(3), 3)
    fake = FakeListings({("Toyota", "RAV4", 2023, "75024"): q})
    assert fake.lookup("Toyota", "RAV4", 2023, "75024") == q
    assert fake.lookup("Toyota", "Camry", 2023, "75024") is None
