"""Shared fixtures: builders for lease and loan customers, no network and no keys."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from crossroads.config import Config
from crossroads.engine.money import payment
from crossroads.engine.schemas import Contract, Customer, EngineInputs, ScenarioInputs

SCENARIO_KEYS = {"miles_per_year", "monthly_budget", "years_to_keep", "financing_rate"}


@pytest.fixture
def cfg() -> Config:
    return Config()


def _build(contract: Contract, cust: dict, scenario: dict) -> EngineInputs:
    sc = dict(miles_per_year=13200, monthly_budget=D(2250), years_to_keep=2, financing_rate=D("6.5"))
    sc.update(scenario)
    return EngineInputs(customer=Customer(contract=contract, **cust), scenario=ScenarioInputs(**sc))


@pytest.fixture
def make_lease():
    """A 36-month SUV lease with 14 months left: payment 389, residual 21,450, worth 22,600."""

    def make(**over) -> EngineInputs:
        o = dict(
            monthly=D(389), months_left=14, residual=D(21450), allowance=36000, fee=D("0.25"),
            today_value=D(22600), current_miles=31200, cls="suv",
            income=D(5200), bills=D(2650), cash=D(4900),
        )
        scenario = {k: over.pop(k) for k in list(over) if k in SCENARIO_KEYS}
        o.update(over)
        contract = Contract(
            type="lease", monthly_payment=o["monthly"], months_left=o["months_left"], term_months=36,
            money_factor=D("0.0015"), cap_cost=D(31000), residual=o["residual"],
            allowance_total_miles=o["allowance"], overage_fee_per_mile=o["fee"],
        )
        cust = dict(
            vehicle_class=o["cls"], current_miles=o["current_miles"], today_value=o["today_value"],
            income=o["income"], bills=o["bills"], cash=o["cash"],
        )
        return _build(contract, cust, scenario)

    return make


@pytest.fixture
def make_loan():
    """A loan with 30 months left on 12,400 at 7.9%, on a car worth 17,600."""

    def make(**over) -> EngineInputs:
        o = dict(
            balance=D(12400), apr=D("7.9"), months_left=30, today_value=D(17600),
            current_miles=40000, cls="sedan", income=D(4800), bills=D(2500), cash=D(5000),
        )
        scenario = dict(miles_per_year=12000, monthly_budget=D(2000), years_to_keep=3)
        scenario.update({k: over.pop(k) for k in list(over) if k in SCENARIO_KEYS})
        o.update(over)
        contract = Contract(
            type="loan", monthly_payment=payment(o["balance"], o["apr"], o["months_left"]),
            months_left=o["months_left"], term_months=60, apr=o["apr"], balance=o["balance"],
        )
        cust = dict(
            vehicle_class=o["cls"], current_miles=o["current_miles"], today_value=o["today_value"],
            income=o["income"], bills=o["bills"], cash=o["cash"],
        )
        return _build(contract, cust, scenario)

    return make


@pytest.fixture(scope="session")
def seed_customers():
    """The 12 seeded synthetic customers, already converted to engine inputs."""
    from crossroads.seed.profiles import load_seed_customers

    return load_seed_customers(Config())
