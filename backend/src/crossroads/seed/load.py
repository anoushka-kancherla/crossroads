"""Seed the database and Nessie from the synthetic profiles.

Run once from the command line: `python -m crossroads.seed.load`. Nessie is seeded here, never at
app startup, and re-running is safe: an entity is created in Nessie only when the database holds
no stored Nessie ID for it. Everything is then read back through the NessieClient into the tables,
so the database mirrors what Nessie returns. Without a `NESSIE_API_KEY` the in-memory fake supplies
the same generated data and the database comes out identical.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import psycopg

from ..adapters.nessie import FakeNessie, HttpNessie, NessieClient
from ..config import load_settings
from ..db.repo import apply_schema, connect, refresh_aggregates
from .profiles import Profile, generate_profiles, synthetic_quote


def _ts(d: date) -> datetime:
    return datetime.combine(d, time(12, 0), tzinfo=UTC)


def upsert_profile(conn: psycopg.Connection, p: Profile) -> None:
    conn.execute(
        """INSERT INTO customers (id, display_name, first_name, zip, lat, lng)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET display_name = EXCLUDED.display_name,
             first_name = EXCLUDED.first_name, zip = EXCLUDED.zip, lat = EXCLUDED.lat,
             lng = EXCLUDED.lng""",
        (p.id, p.display_name, p.first_name, p.zip, p.lat, p.lng),
    )
    v = p.vehicle
    conn.execute(
        """INSERT INTO vehicles (customer_id, year, make, model, trim, vehicle_class,
             original_price, purchase_date, current_odometer)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (customer_id) DO UPDATE SET year = EXCLUDED.year, make = EXCLUDED.make,
             model = EXCLUDED.model, trim = EXCLUDED.trim, vehicle_class = EXCLUDED.vehicle_class,
             original_price = EXCLUDED.original_price, purchase_date = EXCLUDED.purchase_date,
             current_odometer = EXCLUDED.current_odometer""",
        (p.id, v.year, v.make, v.model, v.trim, v.vehicle_class, v.original_price,
         v.purchase_date, v.current_odometer),
    )
    c = p.contract
    conn.execute(
        """INSERT INTO contracts (customer_id, type, start_date, end_date, term_months, months_left,
             monthly_payment, apr, balance, money_factor, cap_cost, residual,
             mileage_allowance_total, overage_fee_per_mile)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (customer_id) DO UPDATE SET type = EXCLUDED.type,
             start_date = EXCLUDED.start_date, end_date = EXCLUDED.end_date,
             term_months = EXCLUDED.term_months, months_left = EXCLUDED.months_left,
             monthly_payment = EXCLUDED.monthly_payment, apr = EXCLUDED.apr,
             balance = EXCLUDED.balance, money_factor = EXCLUDED.money_factor,
             cap_cost = EXCLUDED.cap_cost, residual = EXCLUDED.residual,
             mileage_allowance_total = EXCLUDED.mileage_allowance_total,
             overage_fee_per_mile = EXCLUDED.overage_fee_per_mile""",
        (p.id, c.type, p.start_date, p.end_date, c.term_months, c.months_left, c.monthly_payment,
         c.apr, c.balance, c.money_factor, c.cap_cost, c.residual, c.allowance_total_miles,
         c.overage_fee_per_mile),
    )
    for on, odometer in p.readings:
        conn.execute(
            "INSERT INTO odometer_readings (ts, customer_id, odometer) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (_ts(on), p.id, odometer),
        )
    # Synthetic listing quotes stand in for real local listings (customers meant to have none get no row).
    quote = synthetic_quote(p)
    if quote is not None:
        conn.execute(
            """INSERT INTO listing_cache (make, model, year, zip, low, median, high, n_listings)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (make, model, year, zip) DO UPDATE SET low = EXCLUDED.low,
                 median = EXCLUDED.median, high = EXCLUDED.high, n_listings = EXCLUDED.n_listings""",
            (v.make, v.model, v.year, p.zip, quote.low, quote.median, quote.high, quote.n),
        )


def ensure_in_nessie(conn: psycopg.Connection, nessie: NessieClient, p: Profile) -> str:
    """Create in Nessie whatever the database has no stored ID for, recording each ID at once so
    a crash between two steps never leads to duplicates on the next run. Returns the Nessie
    customer ID."""
    nessie_cid = conn.execute("SELECT nessie_customer_id FROM customers WHERE id = %s", (p.id,)).fetchone()[0]
    if nessie_cid is None:
        nessie_cid = nessie.create_customer(p.first_name, p.last_name, p.zip)
        conn.execute("UPDATE customers SET nessie_customer_id = %s WHERE id = %s", (nessie_cid, p.id))

    accounts = dict(conn.execute("SELECT kind, nessie_account_id FROM accounts WHERE customer_id = %s", (p.id,)))
    for kind, balance in (("checking", p.checking), ("savings", p.savings)):
        if kind not in accounts:
            accounts[kind] = nessie.create_account(nessie_cid, kind, balance)
            conn.execute(
                "INSERT INTO accounts (nessie_account_id, customer_id, kind, balance) VALUES (%s, %s, %s, %s)",
                (accounts[kind], p.id, kind, balance),
            )
    checking = accounts["checking"]

    have = {r[0] for r in conn.execute("SELECT payee FROM bills WHERE customer_id = %s", (p.id,))}
    for payee, amount in p.bills:
        if payee not in have:
            bill_id = nessie.create_bill(checking, payee, amount)
            conn.execute(
                "INSERT INTO bills (nessie_bill_id, customer_id, payee, monthly_amount) VALUES (%s, %s, %s, %s)",
                (bill_id, p.id, payee, amount),
            )

    have = {r[0] for r in conn.execute("SELECT deposited_on FROM income WHERE customer_id = %s", (p.id,))}
    for on, amount in p.deposits:
        if on not in have:
            dep_id = nessie.create_deposit(checking, on, amount, "Payroll")
            conn.execute(
                "INSERT INTO income (nessie_deposit_id, customer_id, deposited_on, monthly_amount) "
                "VALUES (%s, %s, %s, %s)",
                (dep_id, p.id, on, amount),
            )

    have = {
        (r[0], r[1])
        for r in conn.execute(
            "SELECT (ts AT TIME ZONE 'UTC')::date, category FROM transactions WHERE customer_id = %s", (p.id,)
        )
    }
    for on, amount, category in p.transactions:
        if (on, category) not in have:
            pur_id = nessie.create_purchase(checking, on, amount, category)
            conn.execute(
                "INSERT INTO transactions (ts, customer_id, amount, category, nessie_purchase_id) "
                "VALUES (%s, %s, %s, %s, %s)",
                (_ts(on), p.id, amount, category, pur_id),
            )
    return nessie_cid


def read_back(conn: psycopg.Connection, nessie: NessieClient, p: Profile, nessie_cid: str) -> None:
    """Make the tables mirror what Nessie returns."""
    for acct in nessie.get_accounts(nessie_cid):
        conn.execute(
            "UPDATE accounts SET kind = %s, balance = %s, synced_at = now() WHERE nessie_account_id = %s",
            (acct.kind, acct.balance, acct.id),
        )
        if acct.kind != "checking":
            continue
        for b in nessie.get_bills(acct.id):
            conn.execute(
                "UPDATE bills SET payee = %s, monthly_amount = %s WHERE nessie_bill_id = %s",
                (b.payee, b.amount, b.id),
            )
        for d in nessie.get_deposits(acct.id):
            conn.execute(
                "UPDATE income SET deposited_on = %s, monthly_amount = %s WHERE nessie_deposit_id = %s",
                (d.on, d.amount, d.id),
            )
        for t in nessie.get_purchases(acct.id):
            conn.execute(
                "UPDATE transactions SET amount = %s, category = %s WHERE nessie_purchase_id = %s",
                (t.amount, t.category, t.id),
            )


def seed(conn: psycopg.Connection, nessie: NessieClient, profiles: list[Profile]) -> None:
    for p in profiles:
        upsert_profile(conn, p)
        nessie_cid = ensure_in_nessie(conn, nessie, p)
        read_back(conn, nessie, p, nessie_cid)


def main() -> None:
    settings = load_settings()
    conn = connect(settings.database_url, autocommit=True)
    apply_schema(conn)
    nessie: NessieClient = HttpNessie(settings.nessie_api_key) if settings.nessie_api_key else FakeNessie()
    profiles = generate_profiles()
    seed(conn, nessie, profiles)
    refresh_aggregates(conn)
    source = "Nessie" if settings.nessie_api_key else "the in-memory Nessie fake"
    print(f"Seeded {len(profiles)} customers using {source}.")


if __name__ == "__main__":
    main()
