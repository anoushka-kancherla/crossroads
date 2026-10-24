"""Connection helpers and schema setup. Plain SQL through psycopg 3, no ORM."""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

SCHEMA = Path(__file__).with_name("schema.sql")
CONTINUOUS_AGGREGATES = ("monthly_miles", "monthly_payments", "monthly_spend")


def connect(url: str, *, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=autocommit)


def make_pool(url: str, *, min_size: int = 1, max_size: int = 5) -> ConnectionPool:
    """A connection pool for the API processes. The caller opens and closes it."""
    return ConnectionPool(url, min_size=min_size, max_size=max_size, open=False)


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
