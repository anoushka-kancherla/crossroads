"""Dealer ranking by straight-line distance (FR-035). No network."""

from crossroads.adapters.dealers import Dealer, FakeDealers, haversine_miles, nearest

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
