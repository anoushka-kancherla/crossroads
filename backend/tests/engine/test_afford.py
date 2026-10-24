"""Affordability: monthly payment within budget, upfront within cash minus a month of bills."""

from decimal import Decimal as D

from crossroads.engine import afford
from crossroads.engine.paths import BUILDERS


def apply(path, inp, cfg):
    return afford.apply(BUILDERS[path](inp, cfg), inp)


def test_affordable_when_both_tests_pass(make_lease, cfg):
    o = apply("keep_as_is", make_lease(), cfg)
    assert o.affordable and o.shortfalls == []


def test_a_payment_over_budget_is_not_affordable(make_lease, cfg):
    o = apply("buy_out", make_lease(monthly_budget=D(400)), cfg)  # 419.69 vs 400
    assert not o.affordable
    assert [s.kind for s in o.shortfalls] == ["monthly"]
    assert o.shortfalls[0].amount == D("19.69")
    assert "$20" in o.shortfalls[0].text


def test_a_payment_exactly_at_the_budget_is_affordable(make_lease, cfg):
    inp = make_lease(monthly=D(390), monthly_budget=D(390))  # budget moves in $10 steps
    assert apply("keep_as_is", inp, cfg).affordable is True


def test_upfront_cash_shortfall_text_matches_the_computed_amount(make_lease, cfg):
    # needs 7,296 up front; cash 8,746 − bills 2,650 = 6,096 available -> 1,200 short
    o = apply("return_lease_new", make_lease(cash=D(8746)), cfg)
    assert not o.affordable
    assert o.shortfalls[0].amount == D("1200.00")
    assert o.shortfalls[0].text == "needs $1,200 more cash upfront"


def test_upfront_exactly_at_the_available_cash_is_affordable(make_lease, cfg):
    o = apply("return_lease_new", make_lease(cash=D(2650 + 7296)), cfg)
    assert o.affordable


def test_negative_available_cash_fails_every_option_even_with_nothing_due(make_lease, cfg):
    inp = make_lease(cash=D(1000))  # 1,000 − 2,650 bills = −1,650 available
    for path in ("keep_as_is", "buy_out", "return_lease_new", "walk_away"):
        o = apply(path, inp, cfg)
        assert not o.affordable, path
    keep = apply("keep_as_is", inp, cfg)
    assert keep.shortfalls[0].amount == D("1650.00")


def test_both_shortfalls_are_reported(make_lease, cfg):
    o = apply("return_lease_new", make_lease(monthly_budget=D(400), cash=D(3000)), cfg)
    assert {s.kind for s in o.shortfalls} == {"monthly", "cash"}


def test_an_ineligible_option_is_never_affordable(make_loan, cfg):
    o = apply("refinance", make_loan(apr=D("3.4")), cfg)
    assert not o.eligible and o.shortfalls == [] and not o.affordable
