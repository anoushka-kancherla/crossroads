"""Compare the paths for one customer and explain the recommendation.

The engine does all the arithmetic. This module turns a stored customer plus the four slider values
into engine inputs, and the engine's output into the response. The explanation shown with the paths
is the checked template, so it is instant and never needs the model (FR-009, FR-010); the model's
version arrives separately from the explanation route.
"""

from __future__ import annotations

from decimal import Decimal

from ..config import Config
from ..engine.defaults import default_scenario
from ..engine.flips import find_flips
from ..engine.money import fmt_money
from ..engine.recommend import evaluate
from ..engine.schemas import PATH_LABELS, SLIDERS, Customer, EngineInputs, Evaluation
from ..explain import template
from ..explain.facts import build_facts, flip_facts
from ..explain.service import ExplainService, Explanation
from .overview import market_value_of, projection_of
from .schemas import (
    ExplanationOut,
    FlipOut,
    OptionOut,
    PathsRequest,
    PathsResponse,
    RangeOut,
    RecommendationOut,
    ScenarioOut,
    ShortfallOut,
)
from .store import CustomerRecord


class InvalidInput(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


def default_inputs(rec: CustomerRecord, cfg: Config) -> EngineInputs:
    """The customer's own situation with every slider at its default."""
    value, _ = market_value_of(rec, cfg)
    customer = Customer(
        contract=rec.contract,
        vehicle_class=rec.vehicle.vehicle_class,
        current_miles=rec.vehicle.current_odometer,
        today_value=value,
        income=rec.income,
        bills=rec.bills_total,
        cash=rec.checking + rec.savings,
    )
    scenario = default_scenario(customer, projection_of(rec, cfg).default_input, cfg)
    return EngineInputs(customer=customer, scenario=scenario)


def budget_max(default_budget: Decimal) -> Decimal:
    """The standard slider maximum, raised to the customer's own default when that is higher, so
    their own number is always reachable."""
    return max(SLIDERS["monthly_budget"][1], default_budget)


def apply_request(base: EngineInputs, req: PathsRequest) -> EngineInputs:
    given = {k: v for k, v in req.model_dump().items() if v is not None}
    scenario = base.scenario.model_copy(update=given)
    cap = budget_max(base.scenario.monthly_budget)
    if scenario.monthly_budget > cap:
        raise InvalidInput("monthly_budget", f"Monthly budget can be at most {fmt_money(cap)}.")
    return base.model_copy(update={"scenario": scenario})


def _explanation_out(e: Explanation) -> ExplanationOut:
    return ExplanationOut(headline=e.headline, text=e.text, source=e.source, verified=e.verified)


def facts_for(inp: EngineInputs, ev: Evaluation, cfg: Config) -> tuple[dict[str, str], str]:
    return build_facts(inp, ev, cfg)


def assumptions_for(inp: EngineInputs, cfg: Config) -> list[str]:
    """The illustrative values behind the figures, in plain words, each labeled as illustrative."""
    cls, lease = inp.customer.vehicle_class, inp.customer.contract.type == "lease"
    pct = format((cfg.depreciation * 100).normalize(), "f")
    items = [
        f"Your monthly budget starts at your income minus your bills minus {fmt_money(cfg.buffer)} kept free.",
        f"A car you give up before the five years are up is replaced by a lease at "
        f"{fmt_money(cfg.replacement_monthly[cls])} a month with {fmt_money(cfg.replacement_due)} due at signing "
        "(illustrative).",
        f"A car loses {pct}% of its value a year, adjusted by ${cfg.per_mile:.2f} for each mile a year above or "
        f"below {cfg.baseline_miles:,}, and is never worth less than {int(cfg.value_floor * 100)}% of today's "
        "value (illustrative).",
    ]
    if lease:
        items.append(
            f"Returning a lease and leaving Toyota costs a {fmt_money(cfg.disposition_fee)} disposition fee "
            "(illustrative), which is waived when you move into another Toyota."
        )
        items.append(f"A buy out is financed over {cfg.buyout_term_months} months at the financing rate.")
    else:
        items.append(
            f"Paying extra principal adds {fmt_money(cfg.extra_principal_monthly)} a month, or the room left in "
            "your budget if that is less (illustrative)."
        )
    return items


_CONFIRMATIONS = {
    "specialist": "A Toyota Financial Services specialist will contact you to talk through your options.",
    "keep_as_is": "You are staying on your current plan. Nothing changes and your contract continues as it is.",
}


def confirmation_text(path: str, kind: str) -> str:
    """What the customer sees after choosing a next step. No transaction is started."""
    if kind == "specialist":
        return _CONFIRMATIONS["specialist"]
    if path == "keep_as_is":
        return _CONFIRMATIONS["keep_as_is"]
    return (
        f"You chose {PATH_LABELS[path]}. "
        "A Toyota Financial Services specialist will contact you with the next steps."
    )


def build_paths_response(
    inp: EngineInputs, default_budget: Decimal, cfg: Config, explain: ExplainService
) -> PathsResponse:
    ev = evaluate(inp, cfg)
    rec = ev.recommendation
    by = {o.path: o for o in ev.options}
    facts, variant = build_facts(inp, ev, cfg)
    contract_type = inp.customer.contract.type
    hi = budget_max(default_budget)

    flips = []
    for f in find_flips(inp, cfg, budget_hi=hi):
        text = template.flip_sentence(flip_facts(f, contract_type))
        if text is not None:  # a flip sentence that fails the check is dropped, never shown
            flips.append(FlipOut(**f.model_dump(), text=text))

    ranges = {}
    for name, (lo, hi_default, step) in SLIDERS.items():
        ranges[name] = RangeOut(min=lo, max=hi if name == "monthly_budget" else hi_default, step=step)

    return PathsResponse(
        contract_type=contract_type,
        inputs_used=ScenarioOut(**inp.scenario.model_dump()),
        options=[
            OptionOut(
                path=o.path,
                label=o.label,
                eligible=o.eligible,
                ineligible_reason=o.ineligible_reason,
                five_year_cost=o.five_year_cost,
                monthly_payment=o.monthly_payment,
                upfront_cost=o.upfront_cost,
                affordable=o.affordable,
                shortfalls=[ShortfallOut(**s.model_dump()) for s in o.shortfalls],
                tradeoff=template.TRADEOFFS[o.path],
                cumulative_cost=o.cumulative_cost,
            )
            for o in ev.options
        ],
        recommendation=RecommendationOut(
            path=rec.path,
            label=PATH_LABELS[rec.path] if rec.path else None,
            runner_up=rec.runner_up,
            monthly_room_left=rec.monthly_room_left,
            closest_when_none=rec.closest_when_none,
            closest_label=by[rec.closest_when_none].label if rec.closest_when_none else None,
            closest_gap=rec.closest_gap,
            explanation=_explanation_out(explain.template_explanation(facts, variant)),
        ),
        flips=flips,
        ranges=ranges,
        assumptions=assumptions_for(inp, cfg),
    )


def build_explanation(inp: EngineInputs, cfg: Config, explain: ExplainService) -> ExplanationOut:
    """The model's explanation when it is available and passes the number check, else the template."""
    ev = evaluate(inp, cfg)
    facts, variant = build_facts(inp, ev, cfg)
    return _explanation_out(explain.explain(facts, variant))
