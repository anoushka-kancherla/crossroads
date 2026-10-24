"""Dealer ranking by straight-line distance (FR-035). No network."""

import json
from pathlib import Path

import httpx
import pytest

from crossroads.adapters.dealers import (
    Dealer,
    DealerLookupError,
    FakeDealers,
    SerpApiDealers,
    haversine_miles,
    nearest,
    parse_maps_results,
)

PLANO = (33.0762, -96.8239)


def test_haversine_matches_a_known_distance():
    # Plano to downtown Dallas is about 20 miles in a straight line
    assert 19 < haversine_miles(*PLANO, 32.7767, -96.7970) < 22


def test_haversine_is_zero_for_the_same_point_and_symmetric():
    assert haversine_miles(*PLANO, *PLANO) == 0
    a = haversine_miles(*PLANO, 32.78, -96.80)
    assert abs(a - haversine_miles(32.78, -96.80, *PLANO)) < 1e-9


def test_nearest_returns_three_nearest_first_with_distances():
    top = nearest(FakeDealers().search("75024", *PLANO), *PLANO)
    assert len(top) == 3
    distances = [d.distance_miles for d in top]
    assert distances == sorted(distances)
    assert all(d is not None for d in distances)
    assert top[0].name == "Example Toyota North"


def test_nearest_ranks_by_distance_not_input_order():
    far = Dealer("Far", "1 Far Rd", None, None, 40.0, -100.0)
    near = Dealer("Near", "1 Near Rd", None, None, 33.08, -96.82)
    assert [d.name for d in nearest([far, near], *PLANO, n=2)] == ["Near", "Far"]


def test_fewer_candidates_than_requested_is_fine():
    assert nearest([], *PLANO) == []
    one = Dealer("Only", "1 Only Rd", None, None, 33.0, -96.8)
    assert len(nearest([one], *PLANO)) == 1


# --- the captured real SerpApi Google Maps response (task T053) ---

CAPTURED = json.loads((Path(__file__).parent.parent / "fixtures" / "serpapi_maps_toyota.json").read_text())


def test_the_parser_keeps_only_dealerships():
    dealers = parse_maps_results(CAPTURED)
    assert len(dealers) == 12  # of 20 results: the rest are service, parts, used-car and corporate listings
    names = {d.name for d in dealers}
    assert "Toyota of Plano" in names
    assert not any(w in n for n in names for w in ("Service", "Parts", "Pre-Owned", "Motor Sales"))
    assert all(d.name and d.address and d.lat and d.lng for d in dealers)


def test_hours_use_plain_spaces_and_ratings_are_numbers():
    dealers = parse_maps_results(CAPTURED)
    assert all(" " not in d.hours and " " not in d.hours for d in dealers if d.hours)
    assert any(d.hours == "Open · Closes 9 PM" for d in dealers)
    assert all(isinstance(d.rating, float) for d in dealers if d.rating is not None)


def test_the_response_is_in_relevance_order_not_distance_order():
    dealers = parse_maps_results(CAPTURED)
    assert dealers[0].name == "Texas Toyota of Grapevine"  # first in the response, about 16 miles away
    assert nearest(dealers, *PLANO)[0].name == "Toyota of Plano"  # the real nearest, fourth in the response


def test_the_three_nearest_to_plano_are_ranked_by_straight_line_distance():
    top = nearest(parse_maps_results(CAPTURED), *PLANO)
    assert [d.name for d in top][0] == "Toyota of Plano"
    assert len(top) == 3
    assert top[0].distance_miles < 3
    assert [d.distance_miles for d in top] == sorted(d.distance_miles for d in top)


def test_an_empty_search_is_an_empty_list():
    assert parse_maps_results({"error": "Google Maps hasn't returned any results for this query."}) == []
    assert parse_maps_results({"local_results": []}) == []


def test_any_other_error_raises_a_message_that_is_safe_to_show():
    with pytest.raises(DealerLookupError) as e:
        parse_maps_results({"error": "Invalid API key. Your API key should be here: abc123"})
    assert "abc123" not in str(e.value)


def _client(handler) -> SerpApiDealers:
    return SerpApiDealers("SECRETKEY", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_the_client_sends_the_maps_search_and_parses_the_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json=CAPTURED)

    dealers = _client(handler).search("75024", 33.0762, -96.8239)
    assert seen["engine"] == "google_maps" and seen["q"] == "Toyota dealer"
    assert seen["ll"] == "@33.0762,-96.8239,12z" and seen["api_key"] == "SECRETKEY"
    assert len(dealers) == 12


def test_a_failed_request_raises_without_leaking_the_key():
    def server_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("could not connect to https://serpapi.com/search.json?api_key=SECRETKEY")

    for handler in (server_error, unreachable):
        with pytest.raises(DealerLookupError) as e:
            _client(handler).search("75024", 33.0, -96.8)
        assert "SECRETKEY" not in str(e.value) and "api_key" not in str(e.value)
        assert e.value.__cause__ is None and e.value.__suppress_context__  # the URL is not chained along


def test_a_response_that_is_not_json_is_a_lookup_error():
    with pytest.raises(DealerLookupError):
        _client(lambda r: httpx.Response(200, text="<html>not json</html>")).search("75024", 33.0, -96.8)


def test_the_client_needs_a_key():
    with pytest.raises(ValueError):
        SerpApiDealers("")


def test_the_fake_counts_its_searches():
    fake = FakeDealers()
    fake.search("75024", *PLANO)
    fake.search("75024", *PLANO)
    assert fake.calls == 2
