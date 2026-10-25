"""The three kinds of next step a customer can be guided to (Toyota "Guide"), and which kind each path is.

The mapping is an ILLUSTRATIVE ASSUMPTION for the prototype, not Toyota policy: it says which paths a
customer could finish alone, which come with a pre-qualified offer, and which need a person. It lets the
business view show how many recommendations need no specialist time (Toyota "Value: reduce service effort").
"""

from __future__ import annotations

from typing import Literal

from .schemas import PathId

NextStepType = Literal["self_service", "eligible_offer", "specialist_follow_up"]

NEXT_STEP_ORDER: tuple[NextStepType, ...] = ("self_service", "eligible_offer", "specialist_follow_up")

NEXT_STEP_LABELS: dict[NextStepType, str] = {
    "self_service": "Self-service",
    "eligible_offer": "Eligible offer",
    "specialist_follow_up": "Specialist follow-up",
}

NEXT_STEP_TYPES: dict[PathId, NextStepType] = {
    "keep_as_is": "self_service",  # nothing to do
    "extra_principal": "self_service",  # set up the extra payment in the app
    "buy_out": "eligible_offer",  # a Toyota loan offer to accept
    "refinance": "eligible_offer",  # a refinance offer to accept
    "return_lease_new": "specialist_follow_up",  # inspection and new lease paperwork
    "trade_in_early": "specialist_follow_up",  # appraisal and payoff
    "walk_away": "specialist_follow_up",  # a retention conversation before the customer leaves
}


def next_step_of(path: PathId) -> NextStepType:
    return NEXT_STEP_TYPES[path]
