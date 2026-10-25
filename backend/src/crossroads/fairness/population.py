"""The seeded synthetic population for the fairness check.

Written from fixed distributions and a fixed seed, before any result for it was looked at, and it reads
none (FR-020): its parameters are not tuned toward a verdict. Everything is synthetic; no identifying
field carries a real value. Float draws are rounded straight to whole dollars and Decimal.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from ..config import Config, FairnessConfig
from ..customer_api.store import CustomerRecord, VehicleInfo
from ..engine.fairness import band_index
from ..engine.money import cents
from ..engine.schemas import Contract

MEDIAN_INCOME = 5500
INCOME_SPREAD = 0.40
INCOME_RANGE = (2200, 14000)
CATALOGUE = {
    "sedan": ["Camry", "Corolla", "Prius"],
    "suv": ["RAV4", "Highlander", "4Runner"],
    "truck": ["Tacoma", "Tundra"],
}


class PopulationError(ValueError):
    """The generated population cannot support the comparison (a band is too thin)."""


def _round10(x: float) -> Decimal:
    return Decimal(int(round(x / 10)) * 10)


def _whole(x: Decimal | float) -> Decimal:
    return Decimal(x).quantize(Decimal(1), ROUND_HALF_UP)


def _loan(rng: random.Random, pay: Decimal):
    term = rng.choice([48, 60, 72])
    left = rng.randint(6, term - 3)
    apr = Decimal(str(round(rng.uniform(3.5, 10.0), 2)))
    r = apr / 1200
    balance = _whole(pay * (1 - (1 + r) ** -left) / r)
    price = _whole(balance / Decimal(str(round(rng.uniform(0.45, 0.85), 4))))
    contract = Contract(type="loan", monthly_payment=pay, months_left=left, term_months=term, apr=apr, balance=balance)
    return contract, price


def _lease(rng: random.Random, pay: Decimal):
    term = rng.choice([24, 36, 39])
    left = rng.randint(4, term - 2)
    mf = Decimal(str(round(rng.uniform(0.0015, 0.003), 4)))
    # payment = (cap - residual) / term + (cap + residual) * mf, with residual = 60% of cap
    cap = _whole(pay / (Decimal("0.4") / term + Decimal("1.6") * mf))
    contract = Contract(
        type="lease", monthly_payment=pay, months_left=left, term_months=term, money_factor=mf, cap_cost=cap,
        residual=_whole(cap * Decimal("0.6")), allowance_total_miles=12_000 * term // 12,
        overage_fee_per_mile=Decimal("0.25"),
    )
    price = _whole(cap * Decimal(str(round(rng.uniform(1.02, 1.12), 4))))
    return contract, price


def _one(i: int, rng: random.Random, as_of: date) -> CustomerRecord:
    lo, hi = INCOME_RANGE
    income = _round10(min(hi, max(lo, rng.lognormvariate(math.log(MEDIAN_INCOME), INCOME_SPREAD))))
    bills = _round10(1000 + 0.28 * float(income) * (1 + rng.gauss(0, 0.10)))
    is_lease = rng.random() < 0.5
    pay = cents(income * Decimal(str(round(rng.uniform(0.08, 0.16), 4))))
    contract, price = _lease(rng, pay) if is_lease else _loan(rng, pay)
    vclass = rng.choice(list(CATALOGUE))
    model = rng.choice(CATALOGUE[vclass])
    annual = min(22_000, max(6_000, rng.gauss(13_000, 3_500)))
    has_history = rng.random() >= 0.15
    checking = _round10(float(income) * rng.uniform(0.3, 1.6))
    savings = _round10(float(income) * rng.uniform(0.0, 3.0))

    elapsed = contract.term_months - contract.months_left
    bought = as_of - timedelta(days=round(elapsed * 30.44))
    odometer = int(round(annual * elapsed / 12 / 100)) * 100
    readings: list[tuple[date, int]] = []
    if has_history:
        odo, span = 0.0, (as_of - bought).days
        for k in range(elapsed):
            readings.append((bought + timedelta(days=round(span * k / elapsed)), round(odo)))
            odo += annual / 12 * rng.uniform(0.85, 1.15)
        readings.append((as_of, odometer))
    return CustomerRecord(
        id=f"pop_{i:03d}", display_name=f"Synthetic customer {i:03d}", first_name="Synthetic", zip="00000",
        lat=0.0, lng=0.0,
        vehicle=VehicleInfo(as_of.year - elapsed // 12, "Toyota", model, "LE", vclass, price, odometer),
        contract=contract, end_date=as_of + timedelta(days=round(contract.months_left * 30.44)),
        readings=tuple(readings), checking=checking, savings=savings, income=income, bills_total=bills,
        quote=None, quote_updated_at=None,
    )


def generate_population(cfg: FairnessConfig, as_of: date | None = None) -> list[CustomerRecord]:
    """`cfg.population_size` customers, ids pop_001 upward. The same config always gives the same list.
    Raises PopulationError when any income band has fewer than `cfg.min_band_population` customers."""
    rng = random.Random(cfg.population_seed)
    day = as_of or Config().as_of
    people = [_one(i, rng, day) for i in range(1, cfg.population_size + 1)]
    if people:
        counts = [0, 0, 0]
        for p in people:
            counts[band_index(p.income, cfg.band_edges)] += 1
        thin = [n for n in counts if n < cfg.min_band_population]
        if thin:
            raise PopulationError(
                f"An income band has only {min(counts)} customers; each needs at least {cfg.min_band_population}."
            )
    return people
