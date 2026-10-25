"""The staff dashboard's live figures: read the acceptance log, let the engine work the figures out."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ..customer_api.store import CustomerStore
from ..engine.live import AcceptanceEntry, live_figures
from .schemas import LiveResponse


def build_live(store: CustomerStore, now: datetime | None = None) -> LiveResponse:
    """Latest acceptance per customer (picked by the store) in, finished figures out. Raises if the log
    cannot be read; the route turns that into a plain message."""
    entries = [AcceptanceEntry(a.customer_id, a.path, a.retained, a.revenue) for a in store.latest_acceptances()]
    f = live_figures(entries, customers_total=len(store.list_customers()), sequence=store.acceptance_count())
    return LiveResponse(
        accepted_customers=f.accepted_customers,
        customers_total=f.customers_total,
        retained_customers=f.retained_customers,
        retained_pct=f.retained_pct,
        revenue_total=f.revenue_total,
        sequence=f.sequence,
        updated_at=now or datetime.now(UTC),
    )


def etag_of(live: LiveResponse) -> str:
    """A tag that changes when the figures do and not when only the time does."""
    data = live.model_dump(mode="json", exclude={"updated_at"})
    return '"' + hashlib.sha1(repr(sorted(data.items())).encode()).hexdigest()[:16] + '"'
