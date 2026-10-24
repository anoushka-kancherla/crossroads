"""Car value: today's value and the estimated value at a later month (FR-005, FR-034)."""

from __future__ import annotations

from decimal import Decimal

from ..config import Config
from .money import D, cents

_ONE = Decimal(1)


def todays_value(
    listing_median: Decimal | None, original_price: Decimal, age_years: Decimal | int, cfg: Config
) -> tuple[Decimal, str]:
    """Median of local listings when there are any, otherwise a depreciated original price."""
    if listing_median is not None:
        return cents(listing_median), "listings"
    value = D(original_price) * (_ONE - cfg.depreciation) ** D(age_years)
    return cents(value), "original_price"


def value_at(today_value: Decimal, months: int, miles_per_year: int, cfg: Config) -> Decimal:
    """Estimated value `months` from now.

    `today × (1 − rate)^(months/12)`, minus `(miles_per_year − 13,500) × months/12 × per_mile`
    (the mileage baseline is prorated, so it works for any month, and the adjustment applies in
    both directions), never below `value_floor` of today's value.
    """
    today = D(today_value)
    years = D(months) / Decimal(12)
    base = today * (_ONE - cfg.depreciation) ** years
    adjustment = (D(miles_per_year) - D(cfg.baseline_miles)) * years * cfg.per_mile
    return cents(max(base - adjustment, today * cfg.value_floor))
