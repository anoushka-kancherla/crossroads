"""The shared network helpers: the client address the limits are counted against, and the sliding-window
limiter behind the customer API's sync and ask routes (FR-039, FR-041)."""

from types import SimpleNamespace

from crossroads.net import SlidingWindowLimiter, client_ip


def request(peer, forwarded=None):
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer) if peer else None, headers=headers)


def test_a_direct_client_is_its_own_address_and_its_forwarded_header_is_ignored():
    assert client_ip(request("93.184.216.34", "151.101.2.9")) == "93.184.216.34"


def test_behind_the_proxy_the_rightmost_public_forwarded_entry_is_the_client():
    assert client_ip(request("10.0.0.2", "9.9.9.9, 151.101.2.77")) == "151.101.2.77"
    assert client_ip(request("10.0.0.2", "151.101.2.77, 10.0.0.9")) == "151.101.2.77"


def test_with_only_private_hops_the_proxy_address_is_used():
    assert client_ip(request("10.0.0.2", "192.168.1.5")) == "10.0.0.2"
    assert client_ip(request("10.0.0.2")) == "10.0.0.2"


def test_a_request_with_no_peer_is_still_countable():
    assert client_ip(request(None)) == "unknown"


def test_the_limiter_allows_the_limit_then_refuses_with_a_retry_delay():
    now = [1000.0]
    lim = SlidingWindowLimiter(limit=3, window=3600, clock=lambda: now[0])
    assert [lim.hit("a") for _ in range(3)] == [0, 0, 0]
    wait = lim.hit("a")
    assert wait == 3600  # the oldest hit leaves the window an hour after it was made
    now[0] += 1000
    assert lim.hit("a") == 2600


def test_the_oldest_hit_leaving_the_window_frees_a_slot():
    now = [0.0]
    lim = SlidingWindowLimiter(limit=2, window=100, clock=lambda: now[0])
    lim.hit("a")
    now[0] = 60
    lim.hit("a")
    assert lim.hit("a") == 40  # blocked until the first hit expires at t=100
    now[0] = 101
    assert lim.hit("a") == 0


def test_addresses_are_counted_separately():
    lim = SlidingWindowLimiter(limit=1, window=100, clock=lambda: 0.0)
    assert lim.hit("a") == 0 and lim.hit("a") > 0
    assert lim.hit("b") == 0


def test_a_refused_attempt_is_not_counted_so_waiting_always_helps():
    now = [0.0]
    lim = SlidingWindowLimiter(limit=1, window=100, clock=lambda: now[0])
    lim.hit("a")
    for _ in range(50):
        assert lim.hit("a") > 0
    now[0] = 101
    assert lim.hit("a") == 0


def test_idle_addresses_are_forgotten():
    now = [0.0]
    lim = SlidingWindowLimiter(limit=5, window=10, clock=lambda: now[0])
    for i in range(100):
        lim.hit(f"ip{i}")
    now[0] = 1000
    lim.hit("fresh")
    assert len(lim._hits) == 1
