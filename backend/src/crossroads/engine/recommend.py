"""Evaluate every path for a customer and pick the recommendation (FR-008, FR-033)."""

from __future__ import annotations

from ..config import Config
from . import afford
from .money import ZERO
from .paths import build_option
from .schemas import (
    LEASE_PATHS,
    LOAN_PATHS,
    PATH_ORDER,
    EngineInputs,
    Evaluation,
    PathOption,
    Recommendation,
)

_ORDER = {p: i for i, p in enumerate(PATH_ORDER)}


def _rank(o: PathOption):
    """Lowest whole-dollar cost, then lower payment, then lower upfront, then list order."""
    return (o.five_year_cost, o.monthly_payment, o.upfront_cost, _ORDER[o.path])


def recommend(options: list[PathOption], inp: EngineInputs) -> Recommendation:
    ok = sorted((o for o in options if o.eligible and o.affordable), key=_rank)
    if ok:
        best = ok[0]
        return Recommendation(
            path=best.path,
            runner_up=ok[1].path if len(ok) > 1 else None,
            monthly_room_left=max(ZERO, inp.scenario.monthly_budget - best.monthly_payment),
        )
    eligible = [o for o in options if o.eligible]
    if not eligible:
        return Recommendation(path=None)
    closest = min(eligible, key=lambda o: (sum(s.amount for s in o.shortfalls), _ORDER[o.path]))
    return Recommendation(
        path=None,
        closest_when_none=closest.path,
        closest_gap=sum((s.amount for s in closest.shortfalls), ZERO),
    )


def evaluate(inp: EngineInputs, cfg: Config, cache: dict | None = None) -> Evaluation:
    """All options for the customer's contract type, in list order, with the recommendation.
    Pass one `cache` dict across calls that share the same customer to reuse unchanged paths."""
    paths = LEASE_PATHS if inp.customer.contract.type == "lease" else LOAN_PATHS
    options = [afford.apply(build_option(p, inp, cfg, cache), inp) for p in paths]
    return Evaluation(options=options, recommendation=recommend(options, inp))
