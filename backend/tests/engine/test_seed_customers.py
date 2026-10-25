"""The 12 seeded customers: deterministic, varied, and every one runs through the engine."""

import time

from crossroads.config import Config
from crossroads.engine.flips import find_flips
from crossroads.engine.recommend import evaluate
from crossroads.explain import template
from crossroads.explain.facts import build_facts, flip_facts
from crossroads.explain.service import ExplainService
from crossroads.seed.profiles import generate_profiles

CFG = Config()


def test_generation_is_deterministic():
    a, b = generate_profiles(), generate_profiles()
    assert a == b
    assert [p.display_name for p in a] == [p.display_name for p in b]


def test_twelve_customers_six_leases_and_six_loans(seed_customers):
    assert len(seed_customers) == 12
    ids = [s.profile.id for s in seed_customers]
    assert len(set(ids)) == 12
    kinds = [s.profile.contract.type for s in seed_customers]
    assert kinds.count("lease") == 6 and kinds.count("loan") == 6


def test_the_picker_fields_exist_for_everyone(seed_customers):
    for s in seed_customers:
        p = s.profile
        assert p.display_name.strip() and p.vehicle_label and p.zip and p.lat and p.lng


def test_the_edge_cases_are_present(seed_customers):
    by = {s.profile.id: s for s in seed_customers}
    assert by["cust_04"].projection.basis == "allowance"  # one reading, lease
    assert by["cust_11"].projection.basis == "typical_us_driver"  # short history, loan
    assert by["cust_05"].value_basis == "original_price"  # no listings
    assert by["cust_11"].value_basis == "original_price"
    underwater = by["cust_09"].inputs.customer
    assert underwater.contract.balance > underwater.today_value  # negative equity
    for cid in ("cust_04", "cust_11"):  # cash below a month of bills
        c = by[cid].inputs.customer
        assert c.cash < c.bills
    assert by["cust_08"].inputs.customer.contract.apr < 4  # very low APR
    assert by["cust_02"].inputs.customer.contract.months_left <= 3  # lease almost over


def test_the_default_scenario_is_valid_for_everyone(seed_customers):
    for s in seed_customers:
        sc = s.inputs.scenario
        assert 5000 <= sc.miles_per_year <= 25000 and sc.miles_per_year % 100 == 0
        assert sc.monthly_budget >= 200 and sc.monthly_budget % 10 == 0
        assert 1 <= sc.years_to_keep <= 8


def test_every_customer_gets_four_costed_options(seed_customers):
    for s in seed_customers:
        ev = evaluate(s.inputs, CFG)
        assert len(ev.options) == 4, s.profile.id
        for o in ev.options:
            assert len(o.cumulative_cost) == 60 and o.five_year_cost is not None


def test_some_customers_have_a_recommendation_and_some_have_none(seed_customers):
    paths = [evaluate(s.inputs, CFG).recommendation.path for s in seed_customers]
    assert any(p is not None for p in paths)
    assert any(p is None for p in paths)  # the cash-poor customers


def test_evaluation_and_flips_finish_in_time_for_every_customer(seed_customers):
    # SC-004 targets 1 s; 2 s keeps the test from being flaky on a slow machine.
    for s in seed_customers:
        start = time.perf_counter()
        evaluate(s.inputs, CFG)
        find_flips(s.inputs, CFG)
        assert time.perf_counter() - start < 2.0, s.profile.id


def test_the_template_and_flip_sentences_pass_the_number_check_for_everyone(seed_customers):
    service = ExplainService(llm=None)
    for s in seed_customers:
        ev = evaluate(s.inputs, CFG)
        facts, variant = build_facts(s.inputs, ev, CFG)
        e = service.explain(facts, variant)
        assert e.verified and e.source == "template", s.profile.id
        for f in find_flips(s.inputs, CFG):
            assert template.flip_sentence(flip_facts(f, s.profile.contract.type)) is not None


def test_every_customer_has_one_payment_row_per_payment_already_made():
    from crossroads.seed.profiles import payment_history

    for p in generate_profiles():
        rows = payment_history(p)
        made = p.contract.term_months - p.contract.months_left
        assert len(rows) == made, p.id
        dates = [r[0] for r in rows]
        assert dates == sorted(dates) and len(set(dates)) == len(dates)
        assert dates[0] >= p.start_date and dates[-1] <= p.end_date
        for _, amount, principal, interest in rows:
            assert amount == p.contract.monthly_payment and principal + interest == amount and interest >= 0


def test_a_loans_interest_falls_over_time_and_a_leases_rent_charge_is_level():
    from crossroads.seed.profiles import payment_history

    for p in generate_profiles():
        interest = [r[3] for r in payment_history(p)]
        if p.contract.type == "loan" and p.contract.apr > 0 and len(interest) > 1:
            assert interest[0] > interest[-1], p.id
        if p.contract.type == "lease":
            assert len(set(interest)) == 1, p.id
