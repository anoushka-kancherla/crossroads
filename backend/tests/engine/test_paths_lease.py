"""Lease paths: keep as is, buy out, return and lease new, return and walk away (FR-030, FR-031)."""

from decimal import Decimal as D

from crossroads.engine.money import amortize, whole
from crossroads.engine.paths import BUILDERS
from crossroads.engine.valuation import value_at


def option(path, inp, cfg):
    return BUILDERS[path](inp, cfg)


def test_keep_as_is_to_term_then_replacement_lease(make_lease, cfg):
    # 14 × 389 + overage + replacement from month 14.
    # Overage: 31,200 + 13,200 × 14/12 = 46,600 miles vs 36,000 allowed = 10,600 × $0.25 = 2,650.
    o = option("keep_as_is", make_lease(), cfg)
    assert o.five_year_cost == whole(14 * 389 + 2650 + 3000 + 450 * 46)  # 31,796
    assert o.five_year_cost == D(31796)
    assert (o.monthly_payment, o.upfront_cost, o.retained) == (D("389.00"), D("0.00"), True)


def test_overage_is_part_of_the_cost(make_lease, cfg):
    with_overage = option("keep_as_is", make_lease(), cfg)
    without = option("keep_as_is", make_lease(allowance=1_000_000), cfg)
    assert with_overage.five_year_cost - without.five_year_cost == D(2650)


def test_keep_as_is_toyota_revenue_is_the_lease_rent_charge(make_lease, cfg):
    # current lease: 0.0015 × (31,000 + 21,450) × 14 = 1,101.45
    # replacement:   0.0025 × (34,000 + 20,400) × 46 = 6,256.00
    assert option("keep_as_is", make_lease(), cfg).revenue == D("7357.45")


def test_lease_given_up_before_its_term_pays_early_termination_at_that_month(make_lease, cfg):
    # years_to_keep 1 -> month 12, two months before the lease ends.
    # value at 12 = 22,600 × 0.88 − (13,200 − 13,500) × 0.12 = 19,924
    # termination = max(0, 2 × 389 + 21,450 − 19,924) = 2,304, fee waived into a Toyota
    o = option("keep_as_is", make_lease(years_to_keep=1), cfg)
    assert value_at(D(22600), 12, 13200, cfg) == D("19924.00")
    assert o.five_year_cost == D(12 * 389 + 2304 + 3000 + 450 * 48)  # 31,572


def test_buy_out_finances_the_residual_at_the_financing_rate(make_lease, cfg):
    rows = amortize(D(21450), D("6.5"), 60)
    o = option("buy_out", make_lease(years_to_keep=5), cfg)  # keep the car to the horizon
    assert o.monthly_payment == rows[0][0]
    assert o.upfront_cost == D("0.00")
    assert o.five_year_cost == whole(sum(r[0] for r in rows) - value_at(D(22600), 60, 13200, cfg))
    assert o.retained and o.revenue == sum(r[1] for r in rows)


def test_buy_out_given_up_early_sells_the_car_and_replaces_it(make_lease, cfg):
    rows = amortize(D(21450), D("6.5"), 60)
    o = option("buy_out", make_lease(years_to_keep=2), cfg)
    expected = (
        sum(r[0] for r in rows[:24]) + rows[23][3] - value_at(D(22600), 24, 13200, cfg)
        + 3000 + 450 * 36
    )
    assert o.five_year_cost == whole(expected)


def test_buy_out_moves_with_the_financing_rate(make_lease, cfg):
    low = option("buy_out", make_lease(financing_rate=D(4)), cfg)
    high = option("buy_out", make_lease(financing_rate=D(10)), cfg)
    assert low.five_year_cost < high.five_year_cost


def test_return_and_lease_new_pays_termination_now_and_a_new_lease(make_lease, cfg):
    # termination now = 14 × 389 + 21,450 − 22,600 = 4,296; plus 3,000 due at signing
    o = option("return_lease_new", make_lease(), cfg)
    assert o.upfront_cost == D("7296.00")
    assert o.monthly_payment == D("450.00")
    assert o.five_year_cost == D(7296 + 450 * 60)
    assert o.retained and o.revenue > 0


def test_walk_away_pays_the_disposition_fee_that_keep_as_is_waives(make_lease, cfg):
    keep = option("keep_as_is", make_lease(), cfg)
    walk = option("walk_away", make_lease(), cfg)
    assert walk.five_year_cost - keep.five_year_cost == D(395)
    assert (walk.retained, walk.revenue) == (False, D(0))


def test_early_termination_is_zero_when_the_car_is_worth_more_than_the_buyout(make_lease, cfg):
    # worth far more than remaining payments + residual -> no termination charge, no fee
    o = option("return_lease_new", make_lease(today_value=D(40000)), cfg)
    assert o.upfront_cost == D("3000.00")


def test_cumulative_cost_ends_at_the_five_year_cost(make_lease, cfg):
    for path in ("keep_as_is", "buy_out", "return_lease_new", "walk_away"):
        o = option(path, make_lease(), cfg)
        assert len(o.cumulative_cost) == 60
        assert whole(o.cumulative_cost[-1]) == o.five_year_cost
