"""Connection helpers and schema setup. Plain SQL through psycopg 3, no ORM."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from ..adapters.dealers import Dealer

SCHEMA = Path(__file__).with_name("schema.sql")
CONTINUOUS_AGGREGATES = ("monthly_miles", "monthly_payments", "monthly_spend")
# Months are bucketed in UTC, so every session must run in UTC whatever the server default is.
_SESSION = "-c timezone=UTC"


def connect(url: str, *, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=autocommit, options=_SESSION)


def make_pool(url: str, *, min_size: int = 1, max_size: int = 5, timeout: float = 5) -> ConnectionPool:
    """A connection pool for the API processes. The caller opens and closes it. A short timeout
    makes a database outage fail a request quickly, with a readable message, instead of hanging."""
    return ConnectionPool(
        url, kwargs={"options": _SESSION}, min_size=min_size, max_size=max_size, timeout=timeout, open=False
    )


def statements(sql: str) -> list[str]:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def apply_schema(conn: psycopg.Connection) -> None:
    """Create everything that is missing. Safe to run repeatedly.

    Needs an autocommit connection: a continuous aggregate cannot be created inside a
    transaction block.
    """
    if not conn.autocommit:
        raise ValueError("apply_schema needs an autocommit connection")
    for stmt in statements(SCHEMA.read_text()):
        conn.execute(stmt)


def refresh_aggregates(conn: psycopg.Connection) -> None:
    if not conn.autocommit:
        raise ValueError("refresh_aggregates needs an autocommit connection")
    for name in CONTINUOUS_AGGREGATES:
        conn.execute(f"CALL refresh_continuous_aggregate('{name}', NULL, NULL)")


def dealer_candidates(conn: psycopg.Connection, zip_code: str) -> list[Dealer] | None:
    """The cached dealers for a ZIP, or None when that ZIP has never been looked up."""
    rows = conn.execute(
        "SELECT name, address, hours, rating, lat, lng FROM dealer_cache WHERE zip = %s ORDER BY name",
        (zip_code,),
    ).fetchall()
    if not rows:
        return None
    return [
        Dealer(name, address, hours, float(rating) if rating is not None else None, lat, lng)
        for name, address, hours, rating, lat, lng in rows
    ]


def save_dealer_candidates(conn: psycopg.Connection, zip_code: str, dealers: list[Dealer]) -> None:
    for d in dealers:
        conn.execute(
            """INSERT INTO dealer_cache (zip, name, address, hours, rating, lat, lng)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (zip, name, address) DO UPDATE SET hours = EXCLUDED.hours,
                 rating = EXCLUDED.rating, lat = EXCLUDED.lat, lng = EXCLUDED.lng, fetched_at = now()""",
            (zip_code, d.name, d.address, d.hours, d.rating, d.lat, d.lng),
        )


def readings(conn: psycopg.Connection, customer_id: str) -> list[tuple[date, int]]:
    """Every odometer reading, oldest first."""
    rows = conn.execute(
        "SELECT ts, odometer FROM odometer_readings WHERE customer_id = %s ORDER BY ts", (customer_id,)
    ).fetchall()
    return [(ts.date(), odometer) for ts, odometer in rows]


def monthly_miles(conn: psycopg.Connection, customer_id: str) -> list[tuple[date, int]]:
    """Actual miles driven per month, from the monthly_miles aggregate. The aggregate holds the
    highest odometer reading in each month, so a month's miles are the difference from the month
    before; the first month has nothing to subtract from and is left out."""
    rows = conn.execute(
        """SELECT month, odometer - lag(odometer) OVER (ORDER BY month) AS miles
           FROM monthly_miles WHERE customer_id = %s ORDER BY month""",
        (customer_id,),
    ).fetchall()
    return [(month.date(), miles) for month, miles in rows if miles is not None]


def monthly_spend(conn: psycopg.Connection, customer_id: str) -> list[tuple[date, str, Decimal]]:
    """Spending per month and category, from the monthly_spend aggregate."""
    rows = conn.execute(
        "SELECT month, category, amount FROM monthly_spend WHERE customer_id = %s ORDER BY month, category",
        (customer_id,),
    ).fetchall()
    return [(month.date(), category, amount) for month, category, amount in rows]
