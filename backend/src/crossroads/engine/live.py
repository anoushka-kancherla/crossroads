"""The live acceptance figures for the staff dashboard, from the log of accepted recommendations.

Pure `Decimal` code: no clock, randomness or I/O (constitution II). It is given one entry per customer,
each customer's latest acceptance (the stores pick that), so a customer is counted once however many times
they accepted. The browser never adds these up (constitution III).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .money import whole

_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class AcceptanceEntry:
    customer_id: str
    path: str
    retained: bool  # whether that path keeps the customer with Toyota, from the engine
    revenue: Decimal  # the engine's 5-year interest income for that path


@dataclass(frozen=True)
class LiveFigures:
    accepted_customers: int
    customers_total: int
    retained_customers: int
    retained_pct: Decimal | None  # whole percent of those who accepted; None when nobody has
    revenue_total: Decimal  # whole dollars
    sequence: int  # total entries in the log; only ever grows


def live_figures(latest_entries: list[AcceptanceEntry], customers_total: int, sequence: int) -> LiveFigures:
    accepted = len(latest_entries)
    retained = sum(1 for e in latest_entries if e.retained)
    pct = whole(Decimal(retained) * _HUNDRED / accepted) if accepted else None
    revenue = whole(sum((e.revenue for e in latest_entries), Decimal(0)))
    return LiveFigures(accepted, customers_total, retained, pct, revenue, sequence)
