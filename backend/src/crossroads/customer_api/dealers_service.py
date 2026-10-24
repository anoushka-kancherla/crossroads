"""The three nearest Toyota dealers for a customer (FR-035).

Candidates are cached by ZIP, so a customer's screen never waits on a live search once the ZIP has
been looked up (the seed script pre-warms every demo ZIP). Ranking by distance happens here, on every
read, from the customer's own coordinates.
"""

from __future__ import annotations

from ..adapters.dealers import Dealer, DealerLookupError, DealersClient, nearest
from .store import CustomerRecord, CustomerStore


def nearby_dealers(
    store: CustomerStore, client: DealersClient | None, rec: CustomerRecord, n: int = 3
) -> list[Dealer]:
    candidates = store.dealer_candidates(rec.zip)
    if candidates is None:
        if client is None:
            raise DealerLookupError("No dealer source is configured.")
        candidates = client.search(rec.zip, rec.lat, rec.lng)
        if candidates:
            store.save_dealer_candidates(rec.zip, candidates)
    return nearest(candidates, rec.lat, rec.lng, n)
