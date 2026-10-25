"""The "Why not this one?" line for a path that is not the recommendation.

The reason is chosen in a fixed order (not eligible, not affordable, costs more, costs the same) and the
wording is a fixed template whose figures are the engine's own, formatted here and inserted by placeholder.
The line then goes through the same number check as every other explanation, and is left out (None) if it
fails. No model is involved, and the same inputs always give the same line.
"""

from __future__ import annotations

from decimal import Decimal

from ..engine.money import fmt_money
from ..engine.schemas import PathOption
from . import template


def _gap(option: PathOption, kind: str) -> Decimal | None:
    return next((s.amount for s in option.shortfalls if s.kind == kind), None)


def why_not_line(option: PathOption, recommended: PathOption | None, horizon_years: str) -> str | None:
    """One sentence saying why `option` lost to `recommended`, or None (the recommended path itself, a path
    with nothing true to say, or wording that failed the number check). `horizon_years` is the formatted
    horizon, such as "5 years"."""
    if recommended is not None and option.path == recommended.path:
        return None
    facts = {"horizon_years": horizon_years}
    if not option.eligible:
        if not option.ineligible_reason:
            return None
        facts["ineligible_reason"] = option.ineligible_reason
        kind = "not_eligible"
    elif option.shortfalls:
        cash, monthly = _gap(option, "cash"), _gap(option, "monthly")
        bills = option.upfront_cost <= 0  # nothing due up front: the gap is to covering a month of bills
        if cash is not None:
            facts["cash_gap"] = fmt_money(cash)
        if monthly is not None:
            facts["monthly_gap"] = fmt_money(monthly)
        if cash is not None and monthly is not None:
            kind = "both_bills" if bills else "both"
        elif cash is not None:
            kind = "cash_bills" if bills else "cash"
        else:
            kind = "monthly"
    elif recommended is not None:
        diff = option.five_year_cost - recommended.five_year_cost
        if diff < 0:
            return None  # cheaper yet not recommended cannot happen; say nothing rather than something wrong
        if diff == 0:
            kind = "same"
        else:
            facts["cost_gap"] = fmt_money(diff)
            kind = "more"
    else:
        return None
    return template.render_checked(template.WHY_NOT[kind], facts)
