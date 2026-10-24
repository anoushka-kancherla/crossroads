"""Where the per-customer recommendations behind the dashboard are kept (`recommendation_snapshot`).

Written only by the refresh job and read only by the internal API: the customer API never touches this
table, so no cross-customer figure can reach a customer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from psycopg_pool import ConnectionPool

from ..engine.portfolio import CustomerResult


@dataclass(frozen=True)
class SnapshotRow:
    result: CustomerResult
    computed_at: datetime


class SnapshotStore(Protocol):
    def save(self, rows: list[SnapshotRow]) -> None: ...
    def load(self) -> list[SnapshotRow]: ...


class InMemorySnapshots:
    def __init__(self, rows: list[SnapshotRow] | None = None):
        self._rows = {r.result.customer_id: r for r in rows or []}

    def save(self, rows: list[SnapshotRow]) -> None:
        for r in rows:
            self._rows[r.result.customer_id] = r

    def load(self) -> list[SnapshotRow]:
        return [self._rows[k] for k in sorted(self._rows)]


class DbSnapshots:
    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    def save(self, rows: list[SnapshotRow]) -> None:
        with self._pool.connection() as conn:
            for row in rows:
                r = row.result
                conn.execute(
                    """INSERT INTO recommendation_snapshot (customer_id, computed_at, path, five_year_cost,
                         baseline_cost, retained, revenue, explanation_verified)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (customer_id) DO UPDATE SET computed_at = EXCLUDED.computed_at,
                         path = EXCLUDED.path, five_year_cost = EXCLUDED.five_year_cost,
                         baseline_cost = EXCLUDED.baseline_cost, retained = EXCLUDED.retained,
                         revenue = EXCLUDED.revenue, explanation_verified = EXCLUDED.explanation_verified""",
                    (r.customer_id, row.computed_at, r.path, r.five_year_cost, r.baseline_cost, r.retained,
                     r.revenue, r.explanation_verified),
                )

    def load(self) -> list[SnapshotRow]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """SELECT customer_id, computed_at, path, five_year_cost, baseline_cost, retained, revenue,
                          explanation_verified FROM recommendation_snapshot ORDER BY customer_id"""
            ).fetchall()
        return [
            SnapshotRow(
                CustomerResult(cid, path, cost, baseline if baseline is not None else Decimal(0), retained,
                               revenue, verified),
                computed_at,
            )
            for cid, computed_at, path, cost, baseline, retained, revenue, verified in rows
        ]
