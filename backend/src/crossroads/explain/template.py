"""Deterministic explanation text, written only with `{placeholders}` (never raw numbers).

The template goes through the same number check as model text (FR-010). It is shown instantly and
is the fallback when the model is unavailable or its text is rejected.
"""

from __future__ import annotations

from . import numcheck

HEADLINES = {
    "normal": "{path_label}: saves about {savings_5yr} over {horizon_years}",
    "only": "{path_label} fits your budget and cash",
    "none": "No path fits your budget and cash yet",
}

BODIES = {
    "normal": (
        "{path_label} is your best move. Over {horizon_years} it costs {cost_5yr}, which is {savings_5yr} "
        "less than {compare_label}. You'd pay {monthly_payment} a month with {upfront_cost} due up front, "
        "leaving {monthly_room} of room in your budget."
    ),
    "only": (
        "{path_label} is the only path that fits your budget and cash right now. Over "
        "{horizon_years} it costs {cost_5yr}: {monthly_payment} a month, with {upfront_cost} due up front."
    ),
    "none": (
        "None of your paths fit your budget and cash yet. {path_label} comes closest, "
        "but you're {shortfall_amount} short."
    ),
}

TRADEOFFS = {
    "keep_as_is": "No change now. You'd lease a replacement when you give the car up.",
    "buy_out": "You own the car and pay off its financed price.",
    "return_lease_new": "You start a new lease now, after an early return charge.",
    "trade_in_early": "You start a new lease now and pay any gap on the old loan in cash.",
    "refinance": "Same car and loan, at a new rate.",
    "extra_principal": "Your spare monthly budget pays the loan down faster.",
    "walk_away": "You return the car, leave Toyota and pay a fee.",
}

# One short line for each path that is not the recommendation: why it lost. Placeholders only.
WHY_NOT = {
    "not_eligible": "{ineligible_reason}",
    "cash": "Needs {cash_gap} more cash upfront",
    "cash_bills": "Needs {cash_gap} more in the bank to cover a month of bills",
    "monthly": "Monthly payment is {monthly_gap} over your budget",
    "both": "Needs {cash_gap} more cash upfront and {monthly_gap} more monthly budget",
    "both_bills": "Needs {cash_gap} more for bills and {monthly_gap} more monthly budget",
    "more": "Costs {cost_gap} more over {horizon_years}",
    "same": "Costs the same over {horizon_years}",
}

FLIP_SENTENCE = (
    "If {flip_input} changed from {flip_current} to {flip_threshold}, "
    "{flip_to_path} would become the recommendation."
)


def render_checked(template: str, facts: dict[str, str]) -> str | None:
    return numcheck.verify_and_render(template, facts)


def flip_sentence(flip_facts: dict[str, str]) -> str | None:
    """A flip rendered in the backend, so the UI never formats a number itself."""
    return render_checked(FLIP_SENTENCE, flip_facts)
