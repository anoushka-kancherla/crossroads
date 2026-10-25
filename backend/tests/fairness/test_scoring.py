"""score(): the engine's own output, one affordable revenue per affordable option."""

from __future__ import annotations

import time
from decimal import Decimal as D

from crossroads.config import Config, FairnessConfig
from crossroads.customer_api.paths_service import default_inputs
from crossroads.engine.recommend import evaluate
from crossroads.fairness.population import generate_population
from crossroads.fairness.scoring import score
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

CFG = Config()


def demo_records():
    store = InMemoryStore(generate_profiles())
    return [store.get_record(f"cust_{i:02d}") for i in range(1, 13)]


def test_results_equal_the_engines_own_output():
    for rec, res in zip(demo_records(), score(demo_records(), CFG), strict=True):
        ev = evaluate(default_inputs(rec, CFG), CFG)
        affordable = [o for o in ev.options if o.eligible and o.affordable]
        assert res.recommended_path == ev.recommendation.path
        assert res.income == rec.income and res.contract_type == rec.contract.type
        assert sorted(res.affordable_revenues) == sorted(o.revenue for o in affordable)
        assert res.n_affordable == len(affordable)
        if res.recommended_path:
            chosen = next(o for o in affordable if o.path == res.recommended_path)
            assert res.recommended_revenue == chosen.revenue


def test_a_customer_with_no_affordable_option_has_no_recommendation():
    res = score(demo_records(), CFG)
    none = [r for r in res if r.recommended_path is None]
    assert none, "the demo set includes customers with no affordable option"
    assert all(r.affordable_revenues == () and r.recommended_revenue == D(0) for r in none)


def test_walk_away_counts_as_zero_revenue():
    walk = [r for r in score(generate_population(FairnessConfig()), CFG) if r.recommended_path == "walk_away"]
    assert all(r.recommended_revenue == 0 for r in walk)


def test_scoring_500_customers_is_fast():
    people = generate_population(FairnessConfig())
    start = time.perf_counter()
    assert len(score(people, CFG)) == 500
    assert time.perf_counter() - start < 1.0
