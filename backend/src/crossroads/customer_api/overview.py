"""Build the Overview response for one customer from stored data and the engine (FR-002..005, FR-032).

Every figure is computed here or by the engine; the screen only formats it.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ..config import Config
from ..engine import mileage, valuation
from ..engine.money import ZERO, cents
from .schemas import (
    CustomerSummary,
    MarketValue,
    Mileage,
    MileagePoint,
    Money,
    OverviewResponse,
    Projection,
    SpendingPoint,
    SpendingResponse,
    Tiles,
)
from .store import CustomerRecord

_ONE = Decimal(1)


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def _next_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def _whole(x: Decimal) -> int:
    return int(x.quantize(_ONE, ROUND_HALF_UP))


def _basis_label(basis: str, cfg: Config) -> str:
    if basis == "history":
        return "Based on your odometer history"
    if basis == "allowance":
        return "Based on your lease allowance, because there is little odometer history"
    return (
        f"Based on a typical U.S. driver ({cfg.baseline_miles:,} miles a year, illustrative), "
        "because there is little odometer history"
    )


def projection_of(rec: CustomerRecord, cfg: Config) -> mileage.Projection:
    """The mileage projection every screen shares, and so the rate the sliders start from."""
    c = rec.contract
    per_year = c.allowance_total_miles * 12 // c.term_months if c.type == "lease" else None
    return mileage.project(list(rec.readings), c.type, per_year, cfg)


def market_value_of(rec: CustomerRecord, cfg: Config) -> tuple[Decimal, str]:
    """Today's value: the median of the cached listings, else the depreciated original price."""
    if rec.quote is not None:
        return rec.quote.median, "listings"
    value, _ = valuation.todays_value(None, rec.vehicle.original_price, cfg.as_of.year - rec.vehicle.year, cfg)
    return value, "original_price"


def build_overview(rec: CustomerRecord, miles: list[tuple[date, int]], cfg: Config) -> OverviewResponse:
    c, v = rec.contract, rec.vehicle
    lease = c.type == "lease"

    proj = projection_of(rec, cfg)
    rate = proj.default_input  # the same rate the sliders start from, so every screen agrees
    # Whole miles, so the overage and its fee are computed from exactly the miles that are shown.
    end_miles = _whole(mileage.miles_at(v.current_odometer, rate, c.months_left))
    over = int(mileage.overage_miles(Decimal(end_miles), c.allowance_total_miles)) if lease else None

    value, basis = market_value_of(rec, cfg)
    if rec.quote is not None:
        label = f"From {rec.quote.n} local listings"
    else:
        pct = format((cfg.depreciation * 100).normalize(), "f")
        label = (
            f"Estimated from the original price with an illustrative {pct}% yearly depreciation; "
            "no local listings found"
        )

    payoff = c.balance if not lease else c.residual + c.monthly_payment * c.months_left

    if miles:
        last = miles[-1][0]
    elif rec.readings:
        last = rec.readings[-1][0].replace(day=1)
    else:
        last = cfg.as_of.replace(day=1)
    per_month = _whole(Decimal(rate) / 12)
    projected: list[MileagePoint] = []
    month = _next_month(last)
    for _ in range(c.months_left):
        projected.append(MileagePoint(month=_month_key(month), miles=per_month))
        month = _next_month(month)

    return OverviewResponse(
        customer=CustomerSummary(
            id=rec.id,
            first_name=rec.first_name,
            vehicle=f"{v.year} {v.model} {v.trim}",
            contract_type=c.type,
            months_left=c.months_left,
        ),
        tiles=Tiles(
            monthly_payment=cents(c.monthly_payment),
            payments_made=c.term_months - c.months_left,
            payments_total=c.term_months,
            months_left=c.months_left,
            ends_on=rec.end_date,
            payoff_or_buyout=cents(payoff),
            miles_driven=v.current_odometer,
            allowance=c.allowance_total_miles if lease else None,
            equity=cents(value - payoff),
        ),
        mileage=Mileage(
            actual_monthly=[MileagePoint(month=_month_key(m), miles=n) for m, n in miles],
            projected_monthly=projected,
            allowance_per_month=c.allowance_total_miles // c.term_months if lease else None,
            projection=Projection(
                rate_per_year=rate,
                basis=proj.basis,
                basis_label=_basis_label(proj.basis, cfg),
                end_miles=end_miles,
                overage_miles=over,
                overage_fee=cents(over * c.overage_fee_per_mile) if over is not None else None,
            ),
        ),
        money=Money(
            checking=cents(rec.checking),
            savings=cents(rec.savings),
            monthly_income=cents(rec.income),
            monthly_bills=cents(rec.bills_total),
            room_for_payment=cents(max(ZERO, rec.income - rec.bills_total - cfg.buffer)),
        ),
        market_value=MarketValue(
            low=rec.quote.low if rec.quote else None,
            median=cents(value),
            high=rec.quote.high if rec.quote else None,
            n_listings=rec.quote.n if rec.quote else 0,
            updated_at=rec.quote_updated_at,
            basis=basis,
            basis_label=label,
        ),
    )


def build_spending(rows: list[tuple[date, str, Decimal]]) -> SpendingResponse:
    return SpendingResponse(
        months=[SpendingPoint(month=_month_key(m), category=cat, amount=cents(amt)) for m, cat, amt in rows]
    )
