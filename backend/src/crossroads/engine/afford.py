"""Affordability (FR-008, FR-021).

A path is affordable only if both hold: its first-month payment is within the monthly budget, and
its upfront cost is within checking + savings minus one month of bills.
"""

from __future__ import annotations

from .money import cents, fmt_money
from .schemas import EngineInputs, PathOption, Shortfall


def available_cash(inp: EngineInputs):
    return inp.customer.cash - inp.customer.bills


def apply(option: PathOption, inp: EngineInputs) -> PathOption:
    """Return a copy of the option with affordability and any shortfalls filled in."""
    shortfalls: list[Shortfall] = []
    budget = inp.scenario.monthly_budget
    if option.monthly_payment > budget:
        gap = cents(option.monthly_payment - budget)
        shortfalls.append(
            Shortfall(kind="monthly", amount=gap, text=f"monthly payment is {fmt_money(gap)} over your budget")
        )
    cash = available_cash(inp)
    if option.upfront_cost > cash:
        gap = cents(option.upfront_cost - cash)
        shortfalls.append(
            Shortfall(kind="cash", amount=gap, text=f"needs {fmt_money(gap)} more cash upfront")
        )
    return option.model_copy(
        update={"affordable": option.eligible and not shortfalls, "shortfalls": shortfalls}
    )
