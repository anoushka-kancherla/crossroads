"""The seed profiles served through the CustomerStore interface, with no database.

Used by the API tests and handy for running the API without Postgres. It derives monthly miles
and spending the same way the TimescaleDB aggregates do (UTC calendar months), and a database
test checks the two agree.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

from ..adapters.dealers import Dealer
from ..adapters.nessie import NessieClient
from ..customer_api.store import Acceptance, CustomerListEntry, CustomerRecord, NotConnected, VehicleInfo
from ..db.nessie_sync import is_real
from .profiles import AS_OF, Profile, payment_history, synthetic_quote


def _month(d: date) -> date:
    return d.replace(day=1)


class InMemoryStore:
    def __init__(self, profiles: list[Profile]):
        self._profiles = {p.id: p for p in sorted(profiles, key=lambda p: p.id)}
        self._dealers: dict[str, list[Dealer]] = {}
        self._synced: dict[str, datetime] = {}
        self._acceptances: list[Acceptance] = []

    def dealer_candidates(self, zip_code: str) -> list[Dealer] | None:
        return self._dealers.get(zip_code)

    def save_dealer_candidates(self, zip_code: str, dealers: list[Dealer]) -> None:
        self._dealers[zip_code] = list(dealers)

    def record_acceptance(self, entry: Acceptance) -> None:
        self._acceptances.append(entry)

    def latest_acceptances(self) -> list[Acceptance]:
        """One per customer: the latest by time, and the one recorded later when times tie."""
        latest: dict[str, Acceptance] = {}
        for e in self._acceptances:
            if e.customer_id not in latest or e.ts >= latest[e.customer_id].ts:
                latest[e.customer_id] = e
        return [latest[k] for k in sorted(latest)]

    def acceptance_count(self) -> int:
        return len(self._acceptances)

    def list_customers(self) -> list[CustomerListEntry]:
        return [CustomerListEntry(p.id, p.display_name, p.vehicle_label) for p in self._profiles.values()]

    def get_record(self, customer_id: str) -> CustomerRecord | None:
        p = self._profiles.get(customer_id)
        if p is None:
            return None
        v = p.vehicle
        quote = synthetic_quote(p)
        return CustomerRecord(
            id=p.id, display_name=p.display_name, first_name=p.first_name, zip=p.zip, lat=p.lat, lng=p.lng,
            vehicle=VehicleInfo(v.year, v.make, v.model, v.trim, v.vehicle_class, v.original_price,
                                v.current_odometer),
            contract=p.contract, end_date=p.end_date, readings=p.readings,
            checking=p.checking, savings=p.savings, income=p.income,
            bills_total=sum((a for _, a in p.bills), Decimal(0)),
            quote=quote,
            quote_updated_at=datetime.combine(AS_OF, time(12), tzinfo=UTC) if quote else None,
            data_source="nessie" if customer_id in self._synced else "demo",
            synced_at=self._synced.get(customer_id),
        )

    def sync_from_nessie(self, customer_id: str, nessie: NessieClient) -> CustomerRecord | None:
        """Stands in for the database store: only a real client counts as a bank, as in production."""
        if customer_id not in self._profiles:
            return None
        if not is_real(nessie):
            raise NotConnected(customer_id)
        nessie.get_accounts(customer_id)  # the same round trip the database store makes
        self._synced[customer_id] = datetime.now(UTC)
        return self.get_record(customer_id)

    def monthly_miles(self, customer_id: str) -> list[tuple[date, int]]:
        highest: dict[date, int] = {}
        for on, odometer in self._profiles[customer_id].readings:
            key = _month(on)
            highest[key] = max(highest.get(key, odometer), odometer)
        months = sorted(highest)
        return [(m, highest[m] - highest[prev]) for prev, m in zip(months, months[1:], strict=False)]

    def monthly_payments(self, customer_id: str) -> list[tuple[date, Decimal, Decimal, Decimal]]:
        """The payment history summed by UTC calendar month, as the monthly_payments aggregate does."""
        totals: dict[date, tuple[Decimal, Decimal, Decimal]] = {}
        for on, amount, principal, interest in payment_history(self._profiles[customer_id]):
            a, pr, i = totals.get(_month(on), (Decimal(0), Decimal(0), Decimal(0)))
            totals[_month(on)] = (a + amount, pr + principal, i + interest)
        return [(m, *totals[m]) for m in sorted(totals)]

    def monthly_spend(self, customer_id: str) -> list[tuple[date, str, Decimal]]:
        totals: dict[tuple[date, str], Decimal] = {}
        for on, amount, category in self._profiles[customer_id].transactions:
            key = (_month(on), category)
            totals[key] = totals.get(key, Decimal(0)) + amount
        return [(m, cat, amt) for (m, cat), amt in sorted(totals.items())]
