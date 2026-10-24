"""Engine data models (Pydantic v2). The API contracts reuse these shapes."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

PathId = Literal[
    "keep_as_is",
    "buy_out",
    "return_lease_new",
    "trade_in_early",
    "refinance",
    "extra_principal",
    "walk_away",
]
# Fixed list order: also the final tie-break (FR-033).
PATH_ORDER: tuple[PathId, ...] = (
    "keep_as_is",
    "buy_out",
    "return_lease_new",
    "trade_in_early",
    "refinance",
    "extra_principal",
    "walk_away",
)
PATH_LABELS: dict[str, str] = {
    "keep_as_is": "Keep as is",
    "buy_out": "Buy out",
    "return_lease_new": "Return and lease new",
    "trade_in_early": "Trade in early",
    "refinance": "Refinance",
    "extra_principal": "Pay extra principal",
    "walk_away": "Return and walk away",
}
LEASE_PATHS: tuple[PathId, ...] = ("keep_as_is", "buy_out", "return_lease_new", "walk_away")
LOAN_PATHS: tuple[PathId, ...] = ("keep_as_is", "trade_in_early", "refinance", "extra_principal")

# (min, max, step) for each slider, from the wireframe. The budget maximum is raised per customer.
SLIDERS: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    "miles_per_year": (Decimal(5000), Decimal(25000), Decimal(100)),
    "monthly_budget": (Decimal(200), Decimal(1200), Decimal(10)),
    "years_to_keep": (Decimal(1), Decimal(8), Decimal(1)),
    "financing_rate": (Decimal(3), Decimal(12), Decimal("0.25")),
}


class ScenarioInputs(BaseModel):
    miles_per_year: int = Field(ge=5000, le=25000, multiple_of=100)
    # No upper bound here: a customer's own default can exceed the standard slider maximum.
    monthly_budget: Decimal = Field(ge=200, multiple_of=10)
    years_to_keep: int = Field(ge=1, le=8)
    financing_rate: Decimal = Field(ge=3, le=12, multiple_of=Decimal("0.25"))


class Contract(BaseModel):
    type: Literal["lease", "loan"]
    monthly_payment: Decimal
    months_left: int = Field(ge=0)
    term_months: int = Field(gt=0)
    # loan
    apr: Decimal | None = None
    balance: Decimal | None = None
    # lease
    money_factor: Decimal | None = None
    cap_cost: Decimal | None = None
    residual: Decimal | None = None
    allowance_total_miles: int | None = None
    overage_fee_per_mile: Decimal | None = None

    @model_validator(mode="after")
    def _required_fields(self) -> Contract:
        need = (
            ("apr", "balance")
            if self.type == "loan"
            else ("money_factor", "cap_cost", "residual", "allowance_total_miles", "overage_fee_per_mile")
        )
        missing = [n for n in need if getattr(self, n) is None]
        if missing:
            raise ValueError(f"{self.type} contract is missing {', '.join(missing)}")
        if self.type == "loan" and self.months_left < 1:
            raise ValueError("a loan needs at least one month left")
        return self


class Customer(BaseModel):
    contract: Contract
    vehicle_class: Literal["sedan", "suv", "truck"]
    current_miles: int = Field(ge=0)
    today_value: Decimal
    income: Decimal
    bills: Decimal
    cash: Decimal  # checking + savings


class EngineInputs(BaseModel):
    customer: Customer
    scenario: ScenarioInputs


class Shortfall(BaseModel):
    kind: Literal["monthly", "cash"]
    amount: Decimal
    text: str


class PathOption(BaseModel):
    path: PathId
    label: str
    eligible: bool = True
    ineligible_reason: str | None = None
    five_year_cost: Decimal  # whole dollars
    monthly_payment: Decimal  # first-month payment
    upfront_cost: Decimal  # due at signing or at the start
    retained: bool
    revenue: Decimal  # Toyota's 5-year interest income; zero when not retained
    cumulative_cost: list[Decimal]  # months 1..60, ending at five_year_cost
    affordable: bool = False
    shortfalls: list[Shortfall] = Field(default_factory=list)


class Recommendation(BaseModel):
    path: PathId | None
    runner_up: PathId | None = None
    monthly_room_left: Decimal = Decimal(0)
    closest_when_none: PathId | None = None
    closest_gap: Decimal = Decimal(0)


class Evaluation(BaseModel):
    options: list[PathOption]
    recommendation: Recommendation


class Flip(BaseModel):
    input: Literal["miles_per_year", "monthly_budget", "years_to_keep", "financing_rate"]
    current: Decimal
    threshold: Decimal
    to_path: PathId
    relative_change: Decimal
