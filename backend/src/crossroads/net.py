"""Network helpers shared by both APIs: which client address a limit is counted against, and a
sliding-window limiter. Neither API imports the other, so this lives outside both (FR-023, FR-026)."""

from __future__ import annotations

import ipaddress
import math
import time
from collections import deque
from collections.abc import Callable


def _is_private(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def client_ip(request) -> str:
    """The address a limit is counted against. X-Forwarded-For is believed only when the request itself
    comes from the proxy (a private or loopback peer), and then only its rightmost public entry: each
    proxy appends the address it saw, so anything a client wrote earlier in the list is ignored. If every
    entry is private, as on a local Docker network, the proxy's own address is used and everyone shares one
    count."""
    peer = request.client.host if request.client else "unknown"
    if not _is_private(peer):
        return peer
    for hop in reversed([h.strip() for h in request.headers.get("x-forwarded-for", "").split(",")]):
        try:
            ip = ipaddress.ip_address(hop)
        except ValueError:
            continue
        if not (ip.is_private or ip.is_loopback):
            return str(ip)
    return peer


class SlidingWindowLimiter:
    """At most `limit` hits per key in any `window` seconds. `hit` returns 0 when the hit is allowed (and
    counts it), or the whole seconds until a slot frees up when it is not (and counts nothing, so waiting
    always helps). In memory, so a restart clears it. ponytail: shared storage (Redis) if there is ever
    more than one API process."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.time):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> int:
        now = self._clock()
        for k in list(self._hits):  # forget what has aged out, so idle addresses do not pile up
            q = self._hits[k]
            while q and now - q[0] >= self.window:
                q.popleft()
            if not q:
                del self._hits[k]
        q = self._hits.setdefault(key, deque())
        if len(q) >= self.limit:
            return max(1, math.ceil(q[0] + self.window - now))
        q.append(now)
        return 0
