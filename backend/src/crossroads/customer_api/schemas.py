"""Customer API response models. Money is a Decimal and travels as a string (contracts/customer-api.md)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class CustomerListItem(BaseModel):
    """The picker row: nothing but who they are and what they drive (FR-028)."""

    id: str
    display_name: str
    vehicle_label: str


class CustomerSummary(BaseModel):
    id: str
    first_name: str
    vehicle: str
    contract_type: Literal["lease", "loan"]
    months_left: int


class Tiles(BaseModel):
    monthly_payment: Decimal
    payments_made: int
    payments_total: int
    months_left: int
    ends_on: date
    payoff_or_buyout: Decimal
    miles_driven: int
    allowance: int | None  # a loan has no mileage allowance
    equity: Decimal  # market value minus payoff


class MileagePoint(BaseModel):
    month: str  # "YYYY-MM"
    miles: int


class Projection(BaseModel):
    rate_per_year: int
    basis: Literal["history", "allowance", "typical_us_driver"]
    basis_label: str
    end_miles: int
    overage_miles: int | None  # None, not zero, when there is no allowance
    overage_fee: Decimal | None


class Mileage(BaseModel):
    actual_monthly: list[MileagePoint]
    projected_monthly: list[MileagePoint]
    allowance_per_month: int | None
    projection: Projection


class Money(BaseModel):
    checking: Decimal
    savings: Decimal
    monthly_income: Decimal
    monthly_bills: Decimal
    room_for_payment: Decimal


class MarketValue(BaseModel):
    low: Decimal | None
    median: Decimal
    high: Decimal | None
    n_listings: int
    updated_at: datetime | None
    basis: Literal["listings", "original_price"]
    basis_label: str


class OverviewResponse(BaseModel):
    customer: CustomerSummary
    tiles: Tiles
    mileage: Mileage
    money: Money
    market_value: MarketValue


class SpendingPoint(BaseModel):
    month: str  # "YYYY-MM"
    category: str
    amount: Decimal


class SpendingResponse(BaseModel):
    months: list[SpendingPoint]
