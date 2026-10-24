"""Default slider values for a customer (data-model.md, ScenarioInputs)."""

from __future__ import annotations

import math
from decimal import ROUND_FLOOR, Decimal

from ..config import Config
from .schemas import Customer, ScenarioInputs


def default_scenario(customer: Customer, projected_miles_default: int, cfg: Config) -> ScenarioInputs:
    """Budget = income − bills − buffer (floored to a $10 step, never under the slider minimum);
    years to keep = the years left on the contract; rate = the configured default."""
    raw = customer.income - customer.bills - cfg.buffer
    budget = max(Decimal(200), (raw / 10).to_integral_value(ROUND_FLOOR) * 10)
    years = min(8, max(1, math.ceil(customer.contract.months_left / 12)))
    miles = min(25_000, max(5_000, projected_miles_default))
    return ScenarioInputs(
        miles_per_year=miles,
        monthly_budget=budget,
        years_to_keep=years,
        financing_rate=cfg.default_financing_rate,
    )
