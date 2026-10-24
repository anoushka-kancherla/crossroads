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
        "{path_label} is your best next move. Over {horizon_years} it costs {cost_5yr} in total, "
        "{savings_5yr} less than {compare_label}. Your payment would be {monthly_payment} a month "
        "with {upfront_cost} due up front, leaving {monthly_room} of room in your monthly budget."
    ),
    "only": (
        "{path_label} is the only path that fits your budget and cash right now. Over "
        "{horizon_years} it costs {cost_5yr} in total, with a payment of {monthly_payment} a month "
        "and {upfront_cost} due up front."
    ),
    "none": (
        "None of your paths fit your budget and cash right now. {path_label} comes closest, and "
        "it is short by {shortfall_amount}."
    ),
}

TRADEOFFS = {
    "keep_as_is": "No change now, then a replacement lease when the car is given up.",
    "buy_out": "You own the car, with a payment for the financed purchase price.",
    "return_lease_new": "A new lease starts now, after the early return charge.",
    "trade_in_early": "A new lease starts now, and any gap on the old loan is paid in cash.",
    "refinance": "Same car and loan, at a new rate.",
    "extra_principal": "Your spare monthly budget pays the loan down faster.",
    "walk_away": "You return the car and leave Toyota, with a fee at return.",
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
