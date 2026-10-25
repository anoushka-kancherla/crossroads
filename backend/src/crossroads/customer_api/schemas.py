"""Customer API response models. Money is a Decimal and travels as a string (contracts/customer-api.md)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


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
    source: Literal["nessie", "demo"]  # where the balances, income and bills were read from
    source_label: str


class MarketValue(BaseModel):
    low: Decimal | None
    median: Decimal
    high: Decimal | None
    n_listings: int
    updated_at: datetime | None
    basis: Literal["listings", "original_price"]
    basis_label: str
    source: Literal["serpapi", "demo"]  # where the listing prices came from
    source_label: str


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


PathName = Literal[
    "keep_as_is", "buy_out", "return_lease_new", "trade_in_early", "refinance", "extra_principal", "walk_away"
]
InputName = Literal["miles_per_year", "monthly_budget", "years_to_keep", "financing_rate"]


class PathsRequest(BaseModel):
    """Any input left out takes the customer's own default. Ranges are the slider ranges; the budget
    maximum is checked per customer, because a customer's default can sit above the standard one."""

    miles_per_year: int | None = Field(default=None, ge=5000, le=25000, multiple_of=100)
    monthly_budget: Decimal | None = Field(default=None, ge=200, multiple_of=10)
    years_to_keep: int | None = Field(default=None, ge=1, le=8)
    financing_rate: Decimal | None = Field(default=None, ge=3, le=12, multiple_of=Decimal("0.25"))


class ScenarioOut(BaseModel):
    miles_per_year: int
    monthly_budget: Decimal
    years_to_keep: int
    financing_rate: Decimal


class ShortfallOut(BaseModel):
    kind: Literal["monthly", "cash"]
    amount: Decimal
    text: str


class OptionOut(BaseModel):
    path: PathName
    label: str
    eligible: bool
    ineligible_reason: str | None
    five_year_cost: Decimal  # whole dollars
    monthly_payment: Decimal
    upfront_cost: Decimal
    affordable: bool
    shortfalls: list[ShortfallOut]
    tradeoff: str
    cumulative_cost: list[Decimal]  # months 1 to 60


class ExplanationOut(BaseModel):
    headline: str
    text: str
    source: Literal["gemini", "template"]
    verified: bool


class FlipOut(BaseModel):
    input: InputName
    current: Decimal
    threshold: Decimal
    to_path: PathName
    relative_change: Decimal
    text: str  # rendered by the backend, so the screen never formats a number itself


class RecommendationOut(BaseModel):
    path: PathName | None
    label: str | None
    runner_up: PathName | None
    monthly_room_left: Decimal
    closest_when_none: PathName | None
    closest_label: str | None
    closest_gap: Decimal
    explanation: ExplanationOut


class RangeOut(BaseModel):
    min: Decimal
    max: Decimal
    step: Decimal


class PathsResponse(BaseModel):
    contract_type: Literal["lease", "loan"]
    inputs_used: ScenarioOut
    options: list[OptionOut]
    recommendation: RecommendationOut
    flips: list[FlipOut]
    ranges: dict[InputName, RangeOut]
    assumptions: list[str]  # the illustrative values behind the numbers, in plain words (FR-031, FR-034)


class DealerOut(BaseModel):
    name: str
    address: str
    hours: str | None
    rating: float | None
    distance_miles: float


class DealersResponse(BaseModel):
    dealers: list[DealerOut]


class NextStepRequest(BaseModel):
    path: PathName
    kind: Literal["primary", "specialist"]


class NextStepResponse(BaseModel):
    path_label: str
    confirmation: str
    step_type: Literal["self_service", "eligible_offer", "specialist_follow_up"]
    step_label: str
