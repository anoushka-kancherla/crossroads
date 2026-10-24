"""The facts object: named keys mapped to the engine's formatted values.

Every value includes its unit, formatted here with correct singular and plural ("1 year",
"3 years", "13,200 miles"), so explanation text never writes unit words (FR-010).
"""

from __future__ import annotations

from decimal import Decimal

from ..config import Config
from ..engine import paths
from ..engine.money import D, fmt_money
from ..engine.schemas import PATH_LABELS, EngineInputs, Evaluation, Flip

FACT_KEYS = (
    "path_label",
    "alt_path_label",
    "compare_label",
    "cost_5yr",
    "alt_cost_5yr",
    "keep_cost_5yr",
    "savings_5yr",
    "monthly_payment",
    "upfront_cost",
    "monthly_room",
    "monthly_budget",
    "horizon_years",
    "years_to_keep",
    "miles_per_year",
    "financing_rate",
    "overage_fee",
    "shortfall_amount",
)


def fmt_years(n: int) -> str:
    return f"{n} year" if n == 1 else f"{n} years"


def fmt_miles(n: int | Decimal) -> str:
    n = int(n)
    return f"{n:,} mile" if n == 1 else f"{n:,} miles"


def fmt_rate(r: Decimal) -> str:
    return f"{format(D(r).normalize(), 'f')}%"


def build_facts(inp: EngineInputs, ev: Evaluation, cfg: Config) -> tuple[dict[str, str], str]:
    """The facts for the recommendation and which explanation variant applies:
    "normal", "only" (no comparison to make) or "none" (nothing fits)."""
    sc, c = inp.scenario, inp.customer.contract
    by = {o.path: o for o in ev.options}
    rec = ev.recommendation
    overage = paths._overage(inp, c.months_left) if c.type == "lease" else Decimal(0)
    facts = {
        "horizon_years": fmt_years(cfg.horizon_months // 12),
        "years_to_keep": fmt_years(sc.years_to_keep),
        "miles_per_year": fmt_miles(sc.miles_per_year),
        "financing_rate": fmt_rate(sc.financing_rate),
        "monthly_budget": fmt_money(sc.monthly_budget),
        "overage_fee": fmt_money(overage),
        "keep_cost_5yr": fmt_money(by["keep_as_is"].five_year_cost),
    }
    if rec.path is None:
        closest = by.get(rec.closest_when_none) if rec.closest_when_none else None
        facts["path_label"] = closest.label if closest else "Keep as is"
        facts["shortfall_amount"] = fmt_money(rec.closest_gap)
        return facts, "none"
    best = by[rec.path]
    facts.update(
        path_label=best.label,
        cost_5yr=fmt_money(best.five_year_cost),
        monthly_payment=fmt_money(best.monthly_payment),
        upfront_cost=fmt_money(best.upfront_cost),
        monthly_room=fmt_money(rec.monthly_room_left),
    )
    alt = by.get(rec.runner_up) if rec.runner_up else None
    if alt:
        facts["alt_path_label"] = alt.label
        facts["alt_cost_5yr"] = fmt_money(alt.five_year_cost)
    keep = by["keep_as_is"]
    if best.path != "keep_as_is" and keep.five_year_cost >= best.five_year_cost:
        facts["compare_label"] = "keeping your current plan"
        facts["savings_5yr"] = fmt_money(keep.five_year_cost - best.five_year_cost)
        return facts, "normal"
    if alt:
        facts["compare_label"] = alt.label
        facts["savings_5yr"] = fmt_money(alt.five_year_cost - best.five_year_cost)
        return facts, "normal"
    return facts, "only"


_FLIP_LABELS = {
    "miles_per_year": "your miles per year",
    "monthly_budget": "your monthly budget",
    "years_to_keep": "how long you keep the car",
}


def flip_facts(flip: Flip, contract_type: str) -> dict[str, str]:
    """Facts for one flip sentence, with units included."""
    if flip.input == "miles_per_year":
        fmt = fmt_miles
    elif flip.input == "monthly_budget":
        fmt = fmt_money
    elif flip.input == "years_to_keep":
        def fmt(v):
            return fmt_years(int(v))
    else:
        fmt = fmt_rate
    label = _FLIP_LABELS.get(
        flip.input, "your financing rate" if contract_type == "lease" else "your refinance rate"
    )
    return {
        "flip_input": label,
        "flip_current": fmt(flip.current),
        "flip_threshold": fmt(flip.threshold),
        "flip_to_path": PATH_LABELS[flip.to_path],
    }
