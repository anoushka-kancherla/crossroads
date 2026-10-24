"""Recommendation: lowest whole-dollar cost among affordable options, with fixed tie-breaks."""

from decimal import Decimal as D

from crossroads.engine.recommend import evaluate, recommend
from crossroads.engine.schemas import PATH_LABELS, PathOption


def opt(path, cost, monthly=100, upfront=0, **kw) -> PathOption:
    base = dict(
        path=path, label=PATH_LABELS[path], five_year_cost=D(cost), monthly_payment=D(monthly),
        upfront_cost=D(upfront), retained=True, revenue=D(0), cumulative_cost=[],
        affordable=True, eligible=True,
    )
    base.update(kw)
    return PathOption(**base)


def test_each_contract_type_sees_its_own_four_paths_in_list_order(make_lease, make_loan, cfg):
    lease = [o.path for o in evaluate(make_lease(), cfg).options]
    loan = [o.path for o in evaluate(make_loan(), cfg).options]
    assert lease == ["keep_as_is", "buy_out", "return_lease_new", "walk_away"]
    assert loan == ["keep_as_is", "trade_in_early", "refinance", "extra_principal"]


def test_recommends_the_cheapest_affordable_option(make_lease, cfg):
    ev = evaluate(make_lease(), cfg)
    ok = [o for o in ev.options if o.eligible and o.affordable]
    best = min(ok, key=lambda o: o.five_year_cost)
    assert ev.recommendation.path == best.path
    assert ev.recommendation.runner_up is not None


def test_an_unaffordable_cheaper_option_is_skipped(make_lease, cfg):
    cheap = evaluate(make_lease(), cfg).recommendation.path
    assert cheap == "buy_out"
    squeezed = evaluate(make_lease(monthly_budget=D(400)), cfg).recommendation.path  # buy out 419.69
    assert squeezed == "keep_as_is"


def test_monthly_room_left_is_budget_minus_the_payment(make_lease, cfg):
    ev = evaluate(make_lease(), cfg)
    chosen = next(o for o in ev.options if o.path == ev.recommendation.path)
    assert ev.recommendation.monthly_room_left == D(2250) - chosen.monthly_payment


def test_nothing_affordable_returns_the_closest_option_and_the_gap(make_lease, cfg):
    ev = evaluate(make_lease(cash=D(1000)), cfg)  # cash below a month of bills
    rec = ev.recommendation
    assert rec.path is None and rec.closest_when_none is not None
    closest = next(o for o in ev.options if o.path == rec.closest_when_none)
    assert rec.closest_gap == sum(s.amount for s in closest.shortfalls)
    assert rec.closest_gap == min(
        sum(s.amount for s in o.shortfalls) for o in ev.options if o.eligible
    )


def test_ties_go_to_the_lower_monthly_payment(make_lease):
    rec = recommend([opt("keep_as_is", 5000, 200), opt("buy_out", 5000, 150)], make_lease())
    assert rec.path == "buy_out"


def test_then_to_the_lower_upfront_cost(make_lease):
    rec = recommend(
        [opt("keep_as_is", 5000, 150, upfront=500), opt("buy_out", 5000, 150, upfront=100)],
        make_lease(),
    )
    assert rec.path == "buy_out"


def test_then_to_the_fixed_list_order(make_lease):
    rec = recommend([opt("walk_away", 5000), opt("buy_out", 5000), opt("keep_as_is", 5000)], make_lease())
    assert rec.path == "keep_as_is"
    assert rec.runner_up == "buy_out"


def test_costs_are_compared_after_rounding_to_whole_dollars(make_lease, cfg):
    # the engine stores whole-dollar costs, so a sub-dollar difference cannot decide a ranking
    from crossroads.engine.money import whole

    assert whole(D("5000.20")) == whole(D("5000.40"))


def test_an_ineligible_option_is_never_recommended_even_if_cheapest(make_lease):
    cheapest = opt("buy_out", 1000, eligible=False, affordable=False)
    rec = recommend([opt("keep_as_is", 9000), cheapest], make_lease())
    assert rec.path == "keep_as_is"


def test_no_eligible_options_means_no_recommendation_and_no_closest(make_lease):
    rec = recommend([opt("buy_out", 1000, eligible=False, affordable=False)], make_lease())
    assert rec.path is None and rec.closest_when_none is None
