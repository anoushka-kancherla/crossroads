"""Seeded synthetic customers (FR-020): the same seed always gives the same 12 people.

Six leases and six loans, with edge cases on purpose: negative equity, cash-poor customers, a
lease near its end, little or no odometer history, no market listings, a very low APR.
Everything here is synthetic; no real customer data is used anywhere.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal as D

from faker import Faker

from ..adapters.listings import ListingQuote
from ..config import Config
from ..engine import mileage, valuation
from ..engine.defaults import default_scenario
from ..engine.money import cents, payment
from ..engine.schemas import Contract, Customer, EngineInputs

SEED = 42
AS_OF = Config().as_of  # fixed so the data (and the tests) never drift with the calendar

# name, state, zip, latitude, longitude (synthetic home locations for the dealer lookup)
CITIES = [
    ("Plano", "TX", "75024", 33.0762, -96.8239),
    ("Phoenix", "AZ", "85004", 33.4484, -112.0740),
    ("Atlanta", "GA", "30303", 33.7490, -84.3880),
    ("Denver", "CO", "80202", 39.7392, -104.9903),
    ("Seattle", "WA", "98101", 47.6062, -122.3321),
    ("Columbus", "OH", "43215", 39.9612, -82.9988),
]

_BILL_SPLIT = [("Rent or mortgage", "0.62"), ("Utilities", "0.11"), ("Insurance", "0.12"),
               ("Phone", "0.05"), ("Internet", "0.04")]
_SPEND = [("groceries", "0.30"), ("fuel", "0.18"), ("dining", "0.22"), ("shopping", "0.30")]

# Each customer: model, trim, year, class, original price, market listing median (None = no
# listings), annual miles, odometer history ("full", "short" or "one"), starting odometer, monthly
# income, checking, savings, monthly bills, and the contract.
LEASES = [
    dict(id="cust_01", model="RAV4", trim="XLE", year=2023, cls="suv", price=36500, listing=22600,
         annual=15000, hist="full", start=0, income=5200, chk=3100, sav=1800, bills=2650,
         payment=389, ml=14, mf="0.0015", cap=31000, res=21450, allow=12000),
    dict(id="cust_02", model="Camry", trim="SE", year=2022, cls="sedan", price=29500, listing=16900,
         annual=16500, hist="full", start=0, income=4100, chk=2600, sav=900, bills=2300,
         payment=329, ml=3, mf="0.0018", cap=26500, res=17800, allow=12000),
    dict(id="cust_03", model="Tacoma", trim="TRD", year=2023, cls="truck", price=44000, listing=29800,
         annual=11500, hist="full", start=0, income=6800, chk=8000, sav=6000, bills=3100,
         payment=459, ml=20, mf="0.0016", cap=40500, res=24900, allow=12000),
    dict(id="cust_04", model="Highlander", trim="XLE", year=2022, cls="suv", price=46500, listing=27200,
         annual=13000, hist="one", start=0, income=7200, chk=2200, sav=500, bills=3400,
         payment=479, ml=8, mf="0.0017", cap=43000, res=26500, allow=12000),
    dict(id="cust_05", model="Corolla", trim="LE", year=2023, cls="sedan", price=24500, listing=None,
         annual=9500, hist="full", start=0, income=3600, chk=2400, sav=1500, bills=2100,
         payment=289, ml=26, mf="0.0020", cap=23000, res=15200, allow=10000),
    dict(id="cust_06", model="Tundra", trim="Limited", year=2024, cls="truck", price=58000, listing=36100,
         annual=14000, hist="full", start=0, income=9500, chk=12000, sav=9000, bills=4200,
         payment=599, ml=30, mf="0.0014", cap=54000, res=33800, allow=12000),
]
LOANS = [
    dict(id="cust_07", model="Camry", trim="LE", year=2021, cls="sedan", price=26500, listing=17600,
         annual=12500, hist="full", start=18000, income=4800, chk=3500, sav=1500, bills=2500,
         bal=12400, apr="7.9", ml=30),
    dict(id="cust_08", model="RAV4", trim="LE", year=2020, cls="suv", price=30500, listing=19800,
         annual=11000, hist="full", start=15000, income=5400, chk=4000, sav=2500, bills=2600,
         bal=8200, apr="3.4", ml=22),
    dict(id="cust_09", model="Highlander", trim="L", year=2019, cls="suv", price=38000, listing=14100,
         annual=15500, hist="full", start=22000, income=5600, chk=3200, sav=1800, bills=3000,
         bal=15300, apr="9.2", ml=40),
    dict(id="cust_10", model="Tacoma", trim="SR5", year=2022, cls="truck", price=38500, listing=33400,
         annual=13000, hist="full", start=9000, income=8200, chk=9000, sav=5000, bills=3600,
         bal=27800, apr="6.1", ml=54),
    dict(id="cust_11", model="Corolla", trim="S", year=2022, cls="sedan", price=25000, listing=None,
         annual=12000, hist="short", start=12000, income=3900, chk=800, sav=200, bills=2200,
         bal=14200, apr="5.2", ml=36),
    dict(id="cust_12", model="Prius", trim="LE", year=2020, cls="sedan", price=27500, listing=15200,
         annual=9000, hist="full", start=14000, income=5000, chk=6000, sav=3000, bills=2400,
         bal=6100, apr="4.9", ml=14),
]


@dataclass(frozen=True)
class Vehicle:
    year: int
    make: str
    model: str
    trim: str
    vehicle_class: str
    original_price: D
    purchase_date: date
    current_odometer: int


@dataclass(frozen=True)
class Profile:
    id: str
    first_name: str
    last_name: str
    city: str
    state: str
    zip: str
    lat: float
    lng: float
    vehicle: Vehicle
    contract: Contract
    start_date: date
    end_date: date
    readings: tuple[tuple[date, int], ...]
    checking: D
    savings: D
    income: D
    bills: tuple[tuple[str, D], ...]
    deposits: tuple[tuple[date, D], ...]
    transactions: tuple[tuple[date, D, str], ...]
    listing_median: D | None

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def vehicle_label(self) -> str:
        return f"{self.vehicle.model} {self.contract.type}"

    @property
    def allowance_per_year(self) -> int | None:
        c = self.contract
        return c.allowance_total_miles * 12 // c.term_months if c.type == "lease" else None


@dataclass(frozen=True)
class SeedCustomer:
    profile: Profile
    inputs: EngineInputs
    projection: mileage.Projection
    value_basis: str


def synthetic_quote(p: Profile) -> ListingQuote | None:
    """A believable listing range around the profile's median. Synthetic: it stands in for real
    local listings. None for the customers who are meant to have no listings."""
    if p.listing_median is None:
        return None
    m = p.listing_median
    return ListingQuote(
        low=cents(m * D("0.94")), median=cents(m), high=cents(m * D("1.06")), n=6 + int(p.id[-2:]) % 6
    )


def _months_after(start: date, n: int) -> date:
    month = start.month - 1 + n
    return date(start.year + month // 12, month % 12 + 1, min(start.day, 28))


def payment_history(p: Profile) -> list[tuple[date, D, D, D]]:
    """One row per payment already made: (date, amount, principal, interest). A loan's split follows its
    amortization from the original principal (backed out of the payment, term and APR); a lease's
    "interest" is its rent charge, which stays level (the same Toyota income the business view counts)."""
    c = p.contract
    made = c.term_months - c.months_left
    rows: list[tuple[date, D, D, D]] = []
    if c.type == "lease":
        rent = cents((c.cap_cost + c.residual) * c.money_factor)
        for i in range(made):
            rows.append((_months_after(p.start_date, i), c.monthly_payment, c.monthly_payment - rent, rent))
        return rows
    r = c.apr / D(1200)
    bal = c.monthly_payment * c.term_months if r == 0 else c.monthly_payment * (1 - (1 + r) ** -c.term_months) / r
    for i in range(made):
        interest = cents(bal * r)
        principal = c.monthly_payment - interest
        bal -= principal
        rows.append((_months_after(p.start_date, i), c.monthly_payment, principal, interest))
    return rows


def _split(total: int, parts: list[tuple[str, str]], rest: str) -> list[tuple[str, D]]:
    out = [(name, (D(total) * D(p)).quantize(D(1))) for name, p in parts]
    out.append((rest, D(total) - sum(a for _, a in out)))
    return out


def _readings(spec: dict, elapsed_months: int, purchase: date, rng: random.Random):
    annual, start = spec["annual"], spec["start"]
    if spec["hist"] == "one":
        return [(AS_OF, start + round(annual * elapsed_months / 12))]
    if spec["hist"] == "short":
        first = AS_OF - timedelta(days=40)
        return [(first, start + round(annual * elapsed_months / 12)),
                (AS_OF, start + round(annual * (elapsed_months / 12 + 40 / 365.25)))]
    out, odo = [], start
    span = (AS_OF - purchase).days
    for k in range(elapsed_months + 1):
        out.append((purchase + timedelta(days=round(span * k / elapsed_months)), round(odo)))
        odo += annual / 12 * rng.uniform(0.85, 1.15)
    return out


def generate_profiles(seed: int = SEED) -> list[Profile]:
    fake = Faker("en_US")
    fake.seed_instance(seed)
    rng = random.Random(seed)
    profiles: list[Profile] = []
    for i, spec in enumerate(LEASES + LOANS):
        is_lease = "mf" in spec
        city, state, zip_code, lat, lng = CITIES[i % len(CITIES)]
        term = 36 if is_lease else 60
        elapsed = term - spec["ml"]
        purchase = AS_OF - timedelta(days=round(elapsed * 30.44))
        readings = _readings(spec, elapsed, purchase, rng)
        if is_lease:
            contract = Contract(
                type="lease", monthly_payment=D(spec["payment"]), months_left=spec["ml"],
                term_months=term, money_factor=D(spec["mf"]), cap_cost=D(spec["cap"]),
                residual=D(spec["res"]), allowance_total_miles=spec["allow"] * 3,
                overage_fee_per_mile=D("0.25"),
            )
        else:
            contract = Contract(
                type="loan", monthly_payment=payment(spec["bal"], spec["apr"], spec["ml"]),
                months_left=spec["ml"], term_months=term, apr=D(spec["apr"]), balance=D(spec["bal"]),
            )
        income = D(spec["income"])
        profiles.append(Profile(
            id=spec["id"], first_name=fake.first_name(), last_name=fake.last_name(),
            city=city, state=state, zip=zip_code, lat=lat, lng=lng,
            vehicle=Vehicle(spec["year"], "Toyota", spec["model"], spec["trim"], spec["cls"],
                            D(spec["price"]), purchase, readings[-1][1]),
            contract=contract, start_date=purchase,
            end_date=AS_OF + timedelta(days=round(spec["ml"] * 30.44)),
            readings=tuple(readings), checking=D(spec["chk"]), savings=D(spec["sav"]), income=income,
            bills=tuple(_split(spec["bills"], _BILL_SPLIT, "Subscriptions")),
            deposits=tuple((AS_OF - timedelta(days=30 * m), income) for m in range(3)),
            transactions=tuple(
                (AS_OF - timedelta(days=30 * m + 3 * j), amount, category)
                for m in range(6)
                for j, (category, amount) in enumerate(
                    (c, a) for c, a in _split(round(spec["bills"] * 0.6), _SPEND[:-1], _SPEND[-1][0])
                )
            ),
            listing_median=None if spec["listing"] is None else D(spec["listing"]),
        ))
    return profiles


def to_engine(p: Profile, cfg: Config) -> SeedCustomer:
    projection = mileage.project(list(p.readings), p.contract.type, p.allowance_per_year, cfg)
    value, basis = valuation.todays_value(
        p.listing_median, p.vehicle.original_price, AS_OF.year - p.vehicle.year, cfg
    )
    customer = Customer(
        contract=p.contract, vehicle_class=p.vehicle.vehicle_class,
        current_miles=p.vehicle.current_odometer, today_value=value, income=p.income,
        bills=sum((a for _, a in p.bills), D(0)), cash=p.checking + p.savings,
    )
    scenario = default_scenario(customer, projection.default_input, cfg)
    return SeedCustomer(p, EngineInputs(customer=customer, scenario=scenario), projection, basis)


def load_seed_customers(cfg: Config) -> list[SeedCustomer]:
    return [to_engine(p, cfg) for p in generate_profiles()]
