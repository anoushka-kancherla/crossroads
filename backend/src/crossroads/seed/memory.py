"""The seed profiles served through the CustomerStore interface, with no database.

Used by the API tests and handy for running the API without Postgres. It derives monthly miles
and spending the same way the TimescaleDB aggregates do (UTC calendar months), and a database
test checks the two agree.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

from ..customer_api.store import CustomerListEntry, CustomerRecord, VehicleInfo
from .profiles import AS_OF, Profile, synthetic_quote


def _month(d: date) -> date:
    return d.replace(day=1)


class InMemoryStore:
    def __init__(self, profiles: list[Profile]):
        self._profiles = {p.id: p for p in sorted(profiles, key=lambda p: p.id)}

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
        )

    def monthly_miles(self, customer_id: str) -> list[tuple[date, int]]:
        highest: dict[date, int] = {}
        for on, odometer in self._profiles[customer_id].readings:
            key = _month(on)
            highest[key] = max(highest.get(key, odometer), odometer)
        months = sorted(highest)
        return [(m, highest[m] - highest[prev]) for prev, m in zip(months, months[1:], strict=False)]

    def monthly_spend(self, customer_id: str) -> list[tuple[date, str, Decimal]]:
        totals: dict[tuple[date, str], Decimal] = {}
        for on, amount, category in self._profiles[customer_id].transactions:
            key = (_month(on), category)
            totals[key] = totals.get(key, Decimal(0)) + amount
        return [(m, cat, amt) for (m, cat), amt in sorted(totals.items())]
