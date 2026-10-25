"""What the customer API needs from storage, behind an interface (constitution, principle IV).

`DbStore` reads the TimescaleDB tables; `crossroads.seed.memory.InMemoryStore` serves the same
data from the seed profiles, which is what the tests use. Both return only the one customer asked
for, so the API can never hand back another customer's data (FR-024).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from psycopg_pool import ConnectionPool

from ..adapters.dealers import Dealer
from ..adapters.listings import ListingQuote
from ..adapters.nessie import NessieClient
from ..db import repo
from ..db.nessie_sync import is_fake_id, is_real, read_back
from ..engine.schemas import Contract


@dataclass(frozen=True)
class VehicleInfo:
    year: int
    make: str
    model: str
    trim: str
    vehicle_class: str
    original_price: Decimal
    current_odometer: int


@dataclass(frozen=True)
class CustomerListEntry:
    id: str
    display_name: str
    vehicle_label: str


@dataclass(frozen=True)
class CustomerRecord:
    id: str
    display_name: str
    first_name: str
    zip: str
    lat: float
    lng: float
    vehicle: VehicleInfo
    contract: Contract
    end_date: date
    readings: tuple[tuple[date, int], ...]
    checking: Decimal
    savings: Decimal
    income: Decimal  # monthly
    bills_total: Decimal  # monthly
    quote: ListingQuote | None
    quote_updated_at: datetime | None
    data_source: str = "demo"  # "nessie" when the accounts were read back from Capital One Nessie
    quote_source: str = "demo"  # "serpapi" when the market value came from real listings via SerpApi
    synced_at: datetime | None = None  # when the bank figures were last read back from Nessie


@dataclass(frozen=True)
class Acceptance:
    """One logged acceptance: the path a customer pressed, with that path's own engine figures."""

    customer_id: str
    path: str
    retained: bool  # whether the path keeps the customer with Toyota
    revenue: Decimal  # the engine's 5-year interest income for that path
    ts: datetime


class NotConnected(Exception):
    """The customer is demo data with no bank behind it, so there is nothing to sync."""


class CustomerStore(Protocol):
    def list_customers(self) -> list[CustomerListEntry]: ...
    def get_record(self, customer_id: str) -> CustomerRecord | None: ...
    def monthly_miles(self, customer_id: str) -> list[tuple[date, int]]: ...
    def monthly_spend(self, customer_id: str) -> list[tuple[date, str, Decimal]]: ...
    def monthly_payments(self, customer_id: str) -> list[tuple[date, Decimal, Decimal, Decimal]]: ...
    def sync_from_nessie(self, customer_id: str, nessie: NessieClient) -> CustomerRecord | None: ...
    def dealer_candidates(self, zip_code: str) -> list[Dealer] | None: ...
    def save_dealer_candidates(self, zip_code: str, dealers: list[Dealer]) -> None: ...
    def record_acceptance(self, entry: Acceptance) -> None: ...
    def latest_acceptances(self) -> list[Acceptance]: ...
    def acceptance_count(self) -> int: ...


_RECORD_SQL = """
SELECT c.id, c.display_name, c.first_name, c.zip, c.lat, c.lng,
       v.year, v.make, v.model, v.trim, v.vehicle_class, v.original_price, v.current_odometer,
       k.type, k.end_date, k.term_months, k.months_left, k.monthly_payment, k.apr, k.balance,
       k.money_factor, k.cap_cost, k.residual, k.mileage_allowance_total, k.overage_fee_per_mile
FROM customers c
JOIN vehicles v ON v.customer_id = c.id
JOIN contracts k ON k.customer_id = c.id
WHERE c.id = %s
"""


class DbStore:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def record_acceptance(self, entry: Acceptance) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO acceptances (ts, customer_id, path, retained, revenue) VALUES (%s, %s, %s, %s, %s)",
                (entry.ts, entry.customer_id, entry.path, entry.retained, entry.revenue),
            )

    def latest_acceptances(self) -> list[Acceptance]:
        """Each customer's latest acceptance, picked by Tiger Data's own last() aggregate."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                """SELECT customer_id, last(path, ts), last(retained, ts), last(revenue, ts), max(ts)
                   FROM acceptances GROUP BY customer_id ORDER BY customer_id"""
            ).fetchall()
        return [Acceptance(cid, path, retained, revenue, ts) for cid, path, retained, revenue, ts in rows]

    def acceptance_count(self) -> int:
        with self._pool.connection() as conn:
            return conn.execute("SELECT count(*) FROM acceptances").fetchone()[0]

    def list_customers(self) -> list[CustomerListEntry]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """SELECT c.id, c.display_name, v.model, k.type
                   FROM customers c
                   JOIN vehicles v ON v.customer_id = c.id
                   JOIN contracts k ON k.customer_id = c.id
                   ORDER BY c.id"""
            ).fetchall()
        return [CustomerListEntry(i, name, f"{model} {kind}") for i, name, model, kind in rows]

    def get_record(self, customer_id: str) -> CustomerRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(_RECORD_SQL, (customer_id,)).fetchone()
            if row is None:
                return None
            (cid, name, first, zip_code, lat, lng, year, make, model, trim, vclass, price, odometer,
             kind, end_date, term, months_left, payment, apr, balance, mf, cap, residual, allowance,
             fee) = row
            account_rows = conn.execute(
                "SELECT kind, balance, source, synced_at FROM accounts WHERE customer_id = %s", (cid,)
            ).fetchall()
            accounts = {kind: balance for kind, balance, _, _ in account_rows}
            data_source = "nessie" if account_rows and all(r[2] == "nessie" for r in account_rows) else "demo"
            synced_at = max((r[3] for r in account_rows), default=None)
            income = conn.execute(
                "SELECT monthly_amount FROM income WHERE customer_id = %s ORDER BY deposited_on DESC LIMIT 1", (cid,)
            ).fetchone()
            bills = conn.execute(
                "SELECT coalesce(sum(monthly_amount), 0) FROM bills WHERE customer_id = %s", (cid,)
            ).fetchone()[0]
            quote_row = conn.execute(
                """SELECT low, median, high, n_listings, fetched_at, source FROM listing_cache
                   WHERE make = %s AND model = %s AND year = %s AND zip = %s""",
                (make, model, year, zip_code),
            ).fetchone()
            readings = repo.readings(conn, cid)
        contract = Contract(
            type=kind, monthly_payment=payment, months_left=months_left, term_months=term, apr=apr,
            balance=balance, money_factor=mf, cap_cost=cap, residual=residual,
            allowance_total_miles=allowance, overage_fee_per_mile=fee,
        )
        return CustomerRecord(
            id=cid, display_name=name, first_name=first, zip=zip_code, lat=lat, lng=lng,
            vehicle=VehicleInfo(year, make, model, trim, vclass, price, odometer),
            contract=contract, end_date=end_date, readings=tuple(readings),
            checking=accounts.get("checking", Decimal(0)), savings=accounts.get("savings", Decimal(0)),
            income=income[0] if income else Decimal(0), bills_total=bills,
            quote=ListingQuote(*quote_row[:4]) if quote_row else None,
            quote_updated_at=quote_row[4] if quote_row else None,
            data_source=data_source,
            quote_source=quote_row[5] if quote_row else "demo",
            synced_at=synced_at if data_source == "nessie" else None,
        )

    def monthly_miles(self, customer_id: str) -> list[tuple[date, int]]:
        with self._pool.connection() as conn:
            return repo.monthly_miles(conn, customer_id)

    def monthly_spend(self, customer_id: str) -> list[tuple[date, str, Decimal]]:
        with self._pool.connection() as conn:
            return repo.monthly_spend(conn, customer_id)

    def monthly_payments(self, customer_id: str) -> list[tuple[date, Decimal, Decimal, Decimal]]:
        with self._pool.connection() as conn:
            return repo.monthly_payments(conn, customer_id)

    def dealer_candidates(self, zip_code: str) -> list[Dealer] | None:
        with self._pool.connection() as conn:
            return repo.dealer_candidates(conn, zip_code)

    def save_dealer_candidates(self, zip_code: str, dealers: list[Dealer]) -> None:
        with self._pool.connection() as conn:
            repo.save_dealer_candidates(conn, zip_code, dealers)

    def sync_from_nessie(self, customer_id: str, nessie: NessieClient) -> CustomerRecord | None:
        """Re-read this one customer's accounts, bills, deposits and purchases from Nessie. Only a customer
        who already has a real Nessie id and a real client can be synced: demo data has no bank behind it."""
        with self._pool.connection() as conn:
            row = conn.execute("SELECT nessie_customer_id FROM customers WHERE id = %s", (customer_id,)).fetchone()
            if row is None:
                return None
            if not row[0] or is_fake_id(row[0]) or not is_real(nessie):
                raise NotConnected(customer_id)
            read_back(conn, nessie, row[0])
        return self.get_record(customer_id)
