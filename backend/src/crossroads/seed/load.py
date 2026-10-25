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

from ..adapters.dealers import DealerLookupError, DealersClient, SerpApiDealers
from ..adapters.listings import ListingsClient, SerpApiListings
from ..adapters.nessie import FakeNessie, HttpNessie, NessieClient
from ..config import load_settings
from ..db import repo
from ..db.nessie_sync import is_real, read_back, reset_demo_rows
from ..db.repo import apply_schema, compress_old_chunks, compression_stats, connect, refresh_aggregates
from .profiles import Profile, generate_profiles, payment_history, synthetic_quote


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
    for on, amount, principal, interest in payment_history(p):
        conn.execute(
            "INSERT INTO payments (ts, customer_id, amount, principal, interest) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (_ts(on), p.id, amount, principal, interest),
        )
    # Synthetic listing quotes stand in for real local listings (customers meant to have none get no row).
    quote = synthetic_quote(p)
    if quote is not None:
        conn.execute(
            """INSERT INTO listing_cache (make, model, year, zip, low, median, high, n_listings, source)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'demo')
               ON CONFLICT (make, model, year, zip) DO UPDATE SET low = EXCLUDED.low,
                 median = EXCLUDED.median, high = EXCLUDED.high, n_listings = EXCLUDED.n_listings
               WHERE listing_cache.source = 'demo'  -- a real SerpApi quote is never replaced by demo data""",
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


def warm_dealer_cache(conn: psycopg.Connection, dealers: DealersClient, profiles: list[Profile]) -> list[str]:
    """Look up the dealers for every demo ZIP once, so the next-step screen never waits on a live
    search. A ZIP that is already cached is skipped, so re-running costs nothing. Returns the ZIPs that
    failed, by ZIP only: an error message must never carry the request URL, which has the key in it."""
    failed: list[str] = []
    seen: set[str] = set()
    for p in profiles:
        if p.zip in seen:
            continue
        seen.add(p.zip)
        if repo.dealer_candidates(conn, p.zip) is not None:
            continue
        try:
            found = dealers.search(p.zip, p.lat, p.lng)
        except DealerLookupError:
            failed.append(p.zip)
            continue
        repo.save_dealer_candidates(conn, p.zip, found)
    return failed


def warm_listing_cache(
    conn: psycopg.Connection, listings: ListingsClient, profiles: list[Profile]
) -> tuple[int, int]:
    """Look up each distinct car once through SerpApi and cache the quote as 'serpapi'. A car with no
    usable quote, or a failed search, keeps whatever is cached (the demo stand-in), so nothing breaks.
    Returns (cars warmed, cars that fell back). A failure's message never carries the request URL."""
    warmed = fell_back = 0
    seen: set[tuple[str, str, int, str]] = set()
    for p in profiles:
        v = p.vehicle
        key = (v.make, v.model, v.year, p.zip)
        # A customer seeded with no listings on purpose (FR-005's depreciation fallback) stays that way.
        if key in seen or p.listing_median is None:
            continue
        seen.add(key)
        try:
            quote = listings.lookup(*key)
        except RuntimeError:
            quote = None
        if quote is None:
            fell_back += 1
            continue
        conn.execute(
            """INSERT INTO listing_cache (make, model, year, zip, low, median, high, n_listings, source)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'serpapi')
               ON CONFLICT (make, model, year, zip) DO UPDATE SET low = EXCLUDED.low, median = EXCLUDED.median,
                 high = EXCLUDED.high, n_listings = EXCLUDED.n_listings, source = 'serpapi', fetched_at = now()""",
            (*key, quote.low, quote.median, quote.high, quote.n),
        )
        warmed += 1
    return warmed, fell_back


def seed(
    conn: psycopg.Connection,
    nessie: NessieClient,
    profiles: list[Profile],
    dealers: DealersClient | None = None,
    listings: ListingsClient | None = None,
) -> list[str]:
    for p in profiles:
        upsert_profile(conn, p)
        if is_real(nessie):
            reset_demo_rows(conn, p.id)  # a demo seed's fake ids are replaced; real ids are never touched
        nessie_cid = ensure_in_nessie(conn, nessie, p)
        read_back(conn, nessie, nessie_cid)
    if listings is not None:
        warm_listing_cache(conn, listings, profiles)
    return warm_dealer_cache(conn, dealers, profiles) if dealers is not None else []


def refresh_portfolio(database_url: str) -> None:
    """Store every customer's recommendation so the staff dashboard has figures straight away. The
    explanations here are the checked template, so seeding never needs a model key."""
    from ..config import Config
    from ..customer_api.store import DbStore
    from ..db.repo import make_pool
    from ..explain.service import ExplainService
    from ..internal_api.portfolio_service import refresh_snapshots
    from ..internal_api.snapshots import DbSnapshots

    pool = make_pool(database_url)
    pool.open()
    try:
        refresh_snapshots(DbStore(pool), DbSnapshots(pool), Config(), ExplainService(None))
    finally:
        pool.close()


def main() -> None:
    settings = load_settings()
    conn = connect(settings.database_url, autocommit=True)
    apply_schema(conn)
    nessie: NessieClient = HttpNessie(settings.nessie_api_key) if settings.nessie_api_key else FakeNessie()
    profiles = generate_profiles()
    dealers = SerpApiDealers(settings.serpapi_api_key) if settings.serpapi_api_key else None
    listings = SerpApiListings(settings.serpapi_api_key) if settings.serpapi_api_key else None
    failed = seed(conn, nessie, profiles, dealers, listings)
    real = conn.execute("SELECT count(*) FROM listing_cache WHERE source = 'serpapi'").fetchone()[0]
    total = conn.execute("SELECT count(*) FROM listing_cache").fetchone()[0]
    print(f"Market values: {real} of {total} cars from real SerpApi listings, the rest demo data.")
    refresh_aggregates(conn)
    compress_old_chunks(conn)  # the background policy would get to these later; do it now for the demo
    for s in compression_stats(conn):
        print(f"Compression {s.table}: {s.chunks_compressed}/{s.chunks_total} chunks, "
              f"{s.bytes_before:,} -> {s.bytes_after:,} bytes")
    refresh_portfolio(settings.database_url)
    source = "Nessie" if settings.nessie_api_key else "the in-memory Nessie fake"
    print(f"Seeded {len(profiles)} customers using {source}.")
    if dealers is None:
        print("No SERPAPI_API_KEY: nearby dealers will show their unavailable state until one is set.")
    else:
        zips = len({p.zip for p in profiles})
        note = f" Failed: {', '.join(failed)}." if failed else ""
        print(f"Dealer cache ready for {zips - len(failed)} of {zips} ZIPs.{note}")


if __name__ == "__main__":
    main()
