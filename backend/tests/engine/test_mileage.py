"""Mileage projection (FR-003, FR-032)."""

from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from crossroads.config import Config
from crossroads.engine.mileage import miles_at, overage_miles, project

CFG = Config()
D0 = date(2026, 1, 1)


def test_uses_average_miles_per_year_from_first_to_latest_reading():
    p = project([(date(2025, 1, 1), 10000), (date(2026, 1, 1), 23200)], "lease", 12000, CFG)
    assert p.basis == "history"
    assert D("13200") < p.rate_per_year < D("13300")
    assert p.default_input == 13200  # rounded to the nearest 100


def test_readings_in_any_order_give_the_same_result():
    a = [(D0, 10000), (D0 + timedelta(days=200), 16000)]
    assert project(a, "loan", None, CFG) == project(list(reversed(a)), "loan", None, CFG)


def test_less_than_three_months_of_history_falls_back_for_a_lease():
    p = project([(D0, 20000), (D0 + timedelta(days=90), 22000)], "lease", 12000, CFG)
    assert (p.basis, p.rate_per_year, p.default_input) == ("allowance", D(12000), 12000)


def test_ninety_one_days_is_enough_history():
    p = project([(D0, 20000), (D0 + timedelta(days=91), 22000)], "lease", 12000, CFG)
    assert p.basis == "history"


def test_less_than_three_months_falls_back_to_the_typical_driver_for_a_loan():
    p = project([(D0, 20000), (D0 + timedelta(days=30), 21000)], "loan", None, CFG)
    assert (p.basis, p.rate_per_year, p.default_input) == ("typical_us_driver", D(13500), 13500)


def test_one_reading_and_no_readings_use_the_fallback():
    assert project([(D0, 5000)], "lease", 10000, CFG).basis == "allowance"
    assert project([], "loan", None, CFG).basis == "typical_us_driver"


def test_default_input_rounds_half_up_to_the_nearest_hundred():
    assert project([], "lease", 13250, CFG).default_input == 13300
    assert project([], "lease", 13249, CFG).default_input == 13200


def test_decreasing_odometer_is_rejected():
    with pytest.raises(ValueError):
        project([(D0, 9000), (D0 + timedelta(days=200), 8000)], "loan", None, CFG)


def test_end_of_contract_miles_and_overage():
    end = miles_at(31200, 13200, 14)
    assert end == D(46600)
    assert overage_miles(end, 36000) == D(10600)
    assert overage_miles(D(30000), 36000) == 0
