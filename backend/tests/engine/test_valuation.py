"""Car value today and at a later month (FR-005, FR-034)."""

from decimal import Decimal as D

from crossroads.config import Config
from crossroads.engine.valuation import todays_value, value_at

CFG = Config()


def test_todays_value_uses_the_listing_median_when_there_is_one():
    assert todays_value(D("22600"), D(36500), 2, CFG) == (D("22600.00"), "listings")


def test_todays_value_falls_back_to_a_depreciated_original_price():
    # 30,000 × 0.88^2
    assert todays_value(None, D(30000), 2, CFG) == (D("23232.00"), "original_price")


def test_year_five_value_at_the_baseline_mileage():
    # 20,000 × 0.88^5
    assert value_at(D(20000), 60, 13500, CFG) == D("10554.64")


def test_mileage_adjustment_applies_in_both_directions():
    assert value_at(D(20000), 60, 15000, CFG) == D("9654.64")  # 1,500 over × 5 yr × $0.12
    assert value_at(D(20000), 60, 12000, CFG) == D("11454.64")  # fewer miles raises the value
    assert value_at(D(20000), 60, 12000, CFG) > value_at(D(20000), 60, 15000, CFG)


def test_mileage_baseline_is_prorated_for_an_earlier_month():
    # 20,000 × 0.88^2 = 15,488, minus 1,500 × 2 yr × $0.12 = 360
    assert value_at(D(20000), 24, 15000, CFG) == D("15128.00")


def test_value_never_falls_below_the_floor():
    # the formula goes negative; the floor is 10% of today's value
    assert value_at(D(5000), 60, 25000, CFG) == D("500.00")


def test_value_today_is_unchanged_at_the_baseline():
    assert value_at(D(20000), 0, 13500, CFG) == D("20000.00")


def test_fractional_years_use_a_fractional_exponent():
    assert abs(value_at(D(20000), 6, 13500, CFG) - D("18761.66")) <= D("0.01")
