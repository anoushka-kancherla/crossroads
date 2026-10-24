"""Path cost models. Every figure is illustrative and uses exact decimals.

Month 0 is today and `flows[m]` is the net cash paid in month m (negative means cash received).
The horizon is `cfg.horizon_months` (60). A car given up before the horizon is replaced by one
lease that runs to the horizon; a car still owned at the horizon is credited at its estimated
value (FR-030, FR-031, FR-034). The first-month payment and the amount due at the start are what
affordability tests (FR-008); later costs only count toward the 5-year cost.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from ..config import Config
from . import valuation
from .money import ZERO, D, amortize, cents, payment, whole
from .schemas import PATH_LABELS, EngineInputs, PathId, PathOption


def _flows(cfg: Config) -> list[Decimal]:
    return [ZERO] * (cfg.horizon_months + 1)


def _rent_charge(mf: Decimal, cap: Decimal, residual: Decimal, months: int) -> Decimal:
    return cents(mf * (cap + residual) * months)


def _add_replacement(flows: list[Decimal], start: int, cfg: Config, vehicle_class: str) -> Decimal:
    """New lease from month `start` to the horizon. Returns Toyota's rent-charge revenue on it."""
    h = cfg.horizon_months
    if start >= h:
        return ZERO
    flows[start] += cfg.replacement_due
    for m in range(start + 1, h + 1):
        flows[m] += cfg.replacement_monthly[vehicle_class]
    cap = cfg.replacement_cap_cost[vehicle_class]
    return _rent_charge(
        cfg.replacement_money_factor, cap, cap * cfg.replacement_residual_pct, h - start
    )


def _overage(inp: EngineInputs, months: int) -> Decimal:
    c, cust = inp.customer.contract, inp.customer
    miles = D(cust.current_miles) + D(inp.scenario.miles_per_year) * months / 12
    return cents(max(ZERO, miles - c.allowance_total_miles) * c.overage_fee_per_mile)


def lease_termination(inp: EngineInputs, k: int, cfg: Config, fee: Decimal) -> Decimal:
    """Early-termination charge at month k:
    max(0, remaining payments + residual − estimated value at k) + disposition fee."""
    c, cust = inp.customer.contract, inp.customer
    remaining = c.monthly_payment * max(0, c.months_left - k)
    value = valuation.value_at(cust.today_value, k, inp.scenario.miles_per_year, cfg)
    return cents(max(ZERO, remaining + c.residual - value) + fee)


def _lease_run(inp: EngineInputs, cfg: Config, *, toyota_next: bool):
    """Run the current lease to the earlier of its term and the keep period, then replace it.
    Returns (flows, Toyota revenue). The disposition fee is waived only into a Toyota."""
    c, cust, sc = inp.customer.contract, inp.customer, inp.scenario
    h, give_up, ml = cfg.horizon_months, sc.years_to_keep * 12, c.months_left
    flows = _flows(cfg)
    fee = ZERO if toyota_next else cfg.disposition_fee
    paid = min(ml, give_up, h)
    for m in range(1, paid + 1):
        flows[m] += c.monthly_payment
    start: int | None = None
    if give_up < ml and give_up < h:
        flows[give_up] += lease_termination(inp, give_up, cfg, fee)
        start = give_up
    elif ml <= h:
        flows[ml] += _overage(inp, ml) + fee
        start = ml
    revenue = _rent_charge(c.money_factor, c.cap_cost, c.residual, paid)
    if start is not None:
        revenue += _add_replacement(flows, start, cfg, cust.vehicle_class)
    return flows, revenue


def _owned_run(
    inp: EngineInputs, cfg: Config, *, principal: Decimal, apr: Decimal, term: int, extra: Decimal = ZERO
):
    """A financed car: pay the schedule until the keep period ends, then sell it, settle the
    balance (negative equity is paid in cash) and replace it; or keep it and credit its value at
    the horizon. Returns (flows, Toyota interest revenue, first-month payment)."""
    cust, sc = inp.customer, inp.scenario
    h, give_up = cfg.horizon_months, sc.years_to_keep * 12
    rows = amortize(principal, apr, term, extra)
    flows = _flows(cfg)
    interest = ZERO
    for m in range(1, min(len(rows), give_up, h) + 1):
        due, intr, _, _ = rows[m - 1]
        flows[m] += due
        interest += intr
    revenue = interest
    if give_up < h:
        balance = rows[give_up - 1][3] if give_up <= len(rows) else ZERO
        value = valuation.value_at(cust.today_value, give_up, sc.miles_per_year, cfg)
        flows[give_up] += balance - value
        revenue += _add_replacement(flows, give_up, cfg, cust.vehicle_class)
    else:
        if len(rows) > h:
            flows[h] += rows[h - 1][3]
        flows[h] -= valuation.value_at(cust.today_value, h, sc.miles_per_year, cfg)
    first = rows[0][0] if rows else ZERO
    return flows, revenue, first


def _option(
    path: PathId,
    flows: list[Decimal],
    *,
    monthly: Decimal,
    retained: bool,
    revenue: Decimal,
    eligible: bool = True,
    reason: str | None = None,
) -> PathOption:
    run = flows[0]
    cumulative: list[Decimal] = []
    for m in range(1, len(flows)):
        run += flows[m]
        cumulative.append(cents(run))
    return PathOption(
        path=path,
        label=PATH_LABELS[path],
        eligible=eligible,
        ineligible_reason=reason,
        five_year_cost=whole(run),
        monthly_payment=cents(monthly),
        upfront_cost=cents(max(ZERO, flows[0])),
        retained=retained,
        revenue=cents(revenue) if retained else ZERO,
        cumulative_cost=cumulative,
    )


def keep_as_is(inp: EngineInputs, cfg: Config) -> PathOption:
    c = inp.customer.contract
    if c.type == "lease":
        flows, revenue = _lease_run(inp, cfg, toyota_next=True)
        return _option("keep_as_is", flows, monthly=c.monthly_payment, retained=True, revenue=revenue)
    flows, revenue, first = _owned_run(inp, cfg, principal=c.balance, apr=c.apr, term=c.months_left)
    return _option("keep_as_is", flows, monthly=first, retained=True, revenue=revenue)


def walk_away(inp: EngineInputs, cfg: Config) -> PathOption:
    flows, _ = _lease_run(inp, cfg, toyota_next=False)
    return _option(
        "walk_away", flows, monthly=inp.customer.contract.monthly_payment, retained=False, revenue=ZERO
    )


def buy_out(inp: EngineInputs, cfg: Config) -> PathOption:
    """Buy the car now: the residual is financed with Toyota at the financing-rate input."""
    c = inp.customer.contract
    flows, revenue, first = _owned_run(
        inp, cfg, principal=c.residual, apr=inp.scenario.financing_rate, term=cfg.buyout_term_months
    )
    return _option("buy_out", flows, monthly=first, retained=True, revenue=revenue)


def return_lease_new(inp: EngineInputs, cfg: Config) -> PathOption:
    """Return the car now (early termination, fee waived into a Toyota) and start a new lease."""
    cust = inp.customer
    flows = _flows(cfg)
    flows[0] += lease_termination(inp, 0, cfg, ZERO)
    revenue = _add_replacement(flows, 0, cfg, cust.vehicle_class)
    return _option(
        "return_lease_new",
        flows,
        monthly=cfg.replacement_monthly[cust.vehicle_class],
        retained=True,
        revenue=revenue,
    )


def trade_in_early(inp: EngineInputs, cfg: Config) -> PathOption:
    """Loan only: settle the balance from the car's value (a shortfall is paid in cash) and start
    a new Toyota lease now."""
    cust, c = inp.customer, inp.customer.contract
    flows = _flows(cfg)
    flows[0] += c.balance - cust.today_value
    revenue = _add_replacement(flows, 0, cfg, cust.vehicle_class)
    return _option(
        "trade_in_early",
        flows,
        monthly=cfg.replacement_monthly[cust.vehicle_class],
        retained=True,
        revenue=revenue,
    )


def refinance(inp: EngineInputs, cfg: Config) -> PathOption:
    """Loan only: a new loan on the current balance at the financing-rate input, over the
    remaining months. Not eligible when the new rate would not be lower."""
    c, rate = inp.customer.contract, inp.scenario.financing_rate
    flows, revenue, first = _owned_run(
        inp, cfg, principal=c.balance, apr=rate, term=c.months_left
    )
    eligible = rate < c.apr
    return _option(
        "refinance",
        flows,
        monthly=first,
        retained=True,
        revenue=revenue,
        eligible=eligible,
        reason=None if eligible else "Your current rate is already lower than this refinance rate.",
    )


def extra_principal(inp: EngineInputs, cfg: Config) -> PathOption:
    """Loan only: pay a fixed extra amount toward principal every month, or the room left in the
    monthly budget when that is smaller."""
    c, sc = inp.customer.contract, inp.scenario
    room = sc.monthly_budget - payment(c.balance, c.apr, c.months_left)
    extra = min(cfg.extra_principal_monthly, max(ZERO, room))
    flows, revenue, first = _owned_run(
        inp, cfg, principal=c.balance, apr=c.apr, term=c.months_left, extra=extra
    )
    eligible = extra > 0
    return _option(
        "extra_principal",
        flows,
        monthly=first,
        retained=True,
        revenue=revenue,
        eligible=eligible,
        reason=None if eligible else "Your monthly budget leaves no room for extra payments.",
    )


BUILDERS: dict[str, Callable[[EngineInputs, Config], PathOption]] = {
    "keep_as_is": keep_as_is,
    "buy_out": buy_out,
    "return_lease_new": return_lease_new,
    "trade_in_early": trade_in_early,
    "refinance": refinance,
    "extra_principal": extra_principal,
    "walk_away": walk_away,
}

# The scenario inputs each path's cost actually depends on, so the flip search recomputes only
# what a changed input can affect.
RELEVANT: dict[str, tuple[str, ...]] = {
    "keep_as_is": ("miles_per_year", "years_to_keep"),
    "buy_out": ("miles_per_year", "years_to_keep", "financing_rate"),
    "return_lease_new": (),
    "trade_in_early": (),
    "refinance": ("miles_per_year", "years_to_keep", "financing_rate"),
    "extra_principal": ("miles_per_year", "years_to_keep", "monthly_budget"),
    "walk_away": ("miles_per_year", "years_to_keep"),
}


def build_option(path: str, inp: EngineInputs, cfg: Config, cache: dict | None = None) -> PathOption:
    if cache is None:
        return BUILDERS[path](inp, cfg)
    key = (path, tuple(getattr(inp.scenario, f) for f in RELEVANT[path]))
    if key not in cache:
        cache[key] = BUILDERS[path](inp, cfg)
    return cache[key]
