"""Mileage projection (FR-003, FR-032)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ..config import Config
from .money import D

MIN_HISTORY_DAYS = 91  # "at least 3 months" of odometer history


@dataclass(frozen=True)
class Projection:
    rate_per_year: Decimal
    basis: str  # "history" | "allowance" | "typical_us_driver"
    default_input: int  # the rate rounded to the nearest 100: the slider default


def project(
    readings: Sequence[tuple[date, int]],
    contract_type: str,
    allowance_per_year: int | None,
    cfg: Config,
) -> Projection:
    """Average miles per year from the first to the latest reading.

    With less than 3 months of history (or fewer than two readings) a lease falls back to its
    annual allowance and a loan to the configured typical-driver rate; the basis says which.
    """
    ordered = sorted(readings)
    if len(ordered) >= 2:
        (d0, m0), (d1, m1) = ordered[0], ordered[-1]
        span = (d1 - d0).days
        if m1 < m0:
            raise ValueError("odometer readings must not decrease")
        if span >= MIN_HISTORY_DAYS:
            rate = D(m1 - m0) / D(span) * Decimal("365.25")
            return Projection(rate, "history", _round_100(rate))
    if contract_type == "lease" and allowance_per_year:
        rate = D(allowance_per_year)
        return Projection(rate, "allowance", _round_100(rate))
    rate = D(cfg.baseline_miles)
    return Projection(rate, "typical_us_driver", _round_100(rate))


def _round_100(rate: Decimal) -> int:
    return int((rate / 100).quantize(Decimal(1), ROUND_HALF_UP)) * 100


def miles_at(current_miles: int, rate_per_year: int | Decimal, months: int) -> Decimal:
    return D(current_miles) + D(rate_per_year) * D(months) / Decimal(12)


def overage_miles(end_miles: Decimal, allowance_total: int) -> Decimal:
    return max(Decimal(0), end_miles - D(allowance_total))
