"""Loan paths: keep as is, trade in early, refinance, pay extra principal (FR-030, FR-031)."""

from decimal import Decimal as D

from crossroads.engine.money import amortize, payment, whole
from crossroads.engine.paths import BUILDERS
from crossroads.engine.valuation import value_at


def option(path, inp, cfg):
    return BUILDERS[path](inp, cfg)


def test_keep_as_is_owned_to_the_horizon_is_credited_at_its_value(make_loan, cfg):
    rows = amortize(D(12400), D("7.9"), 30)
    o = option("keep_as_is", make_loan(years_to_keep=5), cfg)
    assert o.monthly_payment == payment(12400, D("7.9"), 30)
    assert o.five_year_cost == whole(sum(r[0] for r in rows) - value_at(D(17600), 60, 12000, cfg))
    assert o.retained and o.revenue == sum(r[1] for r in rows)


def test_keep_as_is_sold_after_payoff_is_replaced_by_a_lease(make_loan, cfg):
    # default years_to_keep 3 -> sold at month 36, six months after the loan is paid off
    rows = amortize(D(12400), D("7.9"), 30)
    o = option("keep_as_is", make_loan(), cfg)
    expected = sum(r[0] for r in rows) - value_at(D(17600), 36, 12000, cfg) + 3000 + 380 * 24
    assert o.five_year_cost == whole(expected)


def test_loan_given_up_early_settles_the_balance_from_the_sale(make_loan, cfg):
    rows = amortize(D(12400), D("7.9"), 30)
    o = option("keep_as_is", make_loan(years_to_keep=1), cfg)  # month 12
    expected = (
        sum(r[0] for r in rows[:12]) + rows[11][3] - value_at(D(17600), 12, 12000, cfg)
        + 3000 + 380 * 48
    )
    assert o.five_year_cost == whole(expected)


def test_negative_equity_is_paid_in_cash_when_the_car_is_sold(make_loan, cfg):
    underwater = option("keep_as_is", make_loan(years_to_keep=1, today_value=D(9000)), cfg)
    healthy = option("keep_as_is", make_loan(years_to_keep=1, today_value=D(17600)), cfg)
    assert underwater.five_year_cost > healthy.five_year_cost


def test_trade_in_early_with_a_shortfall_pays_it_in_cash_plus_the_due_at_signing(make_loan, cfg):
    o = option("trade_in_early", make_loan(today_value=D(10000)), cfg)  # 12,400 − 10,000 = 2,400
    assert o.upfront_cost == D("5400.00")
    assert o.monthly_payment == D("380.00")
    assert o.five_year_cost == D(5400 + 380 * 60)


def test_trade_in_early_with_equity_reduces_the_cash_needed(make_loan, cfg):
    o = option("trade_in_early", make_loan(), cfg)  # worth 5,200 more than owed
    assert o.upfront_cost == D("0.00")
    assert o.five_year_cost == D(-2200 + 380 * 60)  # 20,600
    assert o.retained and o.revenue == D("6720.00")  # 0.0025 × (28,000 + 16,800) × 60


def test_refinance_is_eligible_only_when_the_new_rate_is_lower(make_loan, cfg):
    ok = option("refinance", make_loan(), cfg)  # 6.5% vs 7.9%
    assert ok.eligible and ok.ineligible_reason is None
    assert ok.monthly_payment < option("keep_as_is", make_loan(), cfg).monthly_payment
    no = option("refinance", make_loan(apr=D("3.4")), cfg)
    assert not no.eligible and no.ineligible_reason
    assert no.five_year_cost  # still costed, so it can be shown with the reason


def test_extra_principal_adds_a_fixed_amount_when_the_budget_has_room(make_loan, cfg):
    o = option("extra_principal", make_loan(), cfg)  # budget 2,000, plenty of room
    assert o.eligible
    assert o.monthly_payment == payment(12400, D("7.9"), 30) + D(200)  # usual payment plus $200
    keep = option("keep_as_is", make_loan(), cfg)
    assert o.five_year_cost < keep.five_year_cost  # interest saved
    assert o.revenue < keep.revenue


def test_extra_principal_is_capped_at_the_room_left_in_the_budget(make_loan, cfg):
    # payment 456.85, budget 500 -> only 43.15 of room, less than the usual $200
    o = option("extra_principal", make_loan(monthly_budget=D(500)), cfg)
    assert o.eligible and o.monthly_payment == D("500.00")


def test_extra_principal_is_not_eligible_without_room_in_the_budget(make_loan, cfg):
    o = option("extra_principal", make_loan(monthly_budget=D(400)), cfg)
    assert not o.eligible and o.ineligible_reason


def test_cumulative_cost_ends_at_the_five_year_cost(make_loan, cfg):
    for path in ("keep_as_is", "trade_in_early", "refinance", "extra_principal"):
        o = option(path, make_loan(), cfg)
        assert len(o.cumulative_cost) == 60
        assert whole(o.cumulative_cost[-1]) == o.five_year_cost
