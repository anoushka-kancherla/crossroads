"""The 12 demo customers must show the same figures before and after the fairness feature (SC-011)."""

from __future__ import annotations

from decimal import Decimal as D

from crossroads.config import Config
from crossroads.customer_api.paths_service import default_inputs
from crossroads.engine.recommend import evaluate
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

# id: (recommended path, 5-year cost, Toyota revenue)
PINNED = {
    "cust_01": ("buy_out", 25729, "7212.23"),
    "cust_02": ("buy_out", 25581, "6441.32"),
    "cust_03": ("buy_out", 25776, "8448.77"),
    "cust_04": (None, None, None),
    "cust_05": ("buy_out", 16721, "4870.92"),
    "cust_06": ("buy_out", 29461, "8694.11"),
    "cust_07": ("extra_principal", 13123, "3572.92"),
    "cust_08": ("extra_principal", 11598, "5075.32"),
    "cust_09": ("extra_principal", 17855, "3282.28"),
    "cust_10": ("extra_principal", 12421, "2907.46"),
    "cust_11": (None, None, None),
    "cust_12": ("extra_principal", 10086, "4165.12"),
}


def test_the_demo_customers_are_unchanged():
    cfg, store = Config(), InMemoryStore(generate_profiles())
    total, recommended = D(0), 0
    for cid, (path, cost, revenue) in PINNED.items():
        ev = evaluate(default_inputs(store.get_record(cid), cfg), cfg)
        assert ev.recommendation.path == path, cid
        if path is None:
            continue
        opt = next(o for o in ev.options if o.path == path)
        assert (int(opt.five_year_cost), opt.revenue) == (cost, D(revenue)), cid
        total += opt.revenue
        recommended += 1
    assert total == D("54670.45")
    assert recommended == 10
