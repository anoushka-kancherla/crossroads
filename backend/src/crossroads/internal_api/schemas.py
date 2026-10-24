"""Internal API models. Money and percentages travel as strings, like the customer API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

PathName = Literal[
    "keep_as_is", "buy_out", "return_lease_new", "trade_in_early", "refinance", "extra_principal", "walk_away"
]


class LoginRequest(BaseModel):
    username: str = Field(max_length=256)
    password: str = Field(max_length=1024)


class SessionOut(BaseModel):
    user: str


class KpisOut(BaseModel):
    retained_count: int
    retained_pct: Decimal
    revenue_total: Decimal
    avg_savings: Decimal
    explanations_verified_pct: Decimal


class PathRowOut(BaseModel):
    path: PathName
    label: str
    customers: int
    share_pct: Decimal
    stays_with_toyota: bool
    stays_label: str
    revenue: Decimal


class PortfolioResponse(BaseModel):
    empty: bool
    computed_at: datetime | None
    customers_total: int
    no_recommendation: int
    kpis: KpisOut
    by_path: list[PathRowOut]
    assumptions: list[str]
