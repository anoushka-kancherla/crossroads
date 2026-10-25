"""Slot filling and the number check (FR-010, SC-003, constitution principle III)."""

from decimal import Decimal as D

import pytest

from crossroads.engine.flips import find_flips
from crossroads.engine.recommend import evaluate
from crossroads.engine.schemas import Flip
from crossroads.explain import numcheck, template
from crossroads.explain.facts import (
    FACT_KEYS,
    build_facts,
    flip_facts,
    fmt_miles,
    fmt_rate,
    fmt_years,
)

FACTS = {k: "x" for k in FACT_KEYS}


def test_a_digit_outside_a_placeholder_is_rejected():
    assert numcheck.check("It costs {cost_5yr} over 5 years.", FACTS)
    assert numcheck.check("Pay $400 a month.", FACTS)


@pytest.mark.parametrize("word", ["one", "One", "two", "twenty-five", "hundred", "thousand"])
def test_a_spelled_out_number_outside_a_placeholder_is_rejected(word):
    assert numcheck.check(f"This is {word} option.", FACTS)


def test_an_unknown_placeholder_is_rejected():
    assert numcheck.check("Your {mystery_figure} is large.", FACTS)
    assert numcheck.check("Empty {} slot.", FACTS)


def test_a_malformed_placeholder_is_rejected():
    assert numcheck.check("Cost {cost_5yr is large.", FACTS)


def test_text_made_only_of_known_placeholders_passes():
    assert numcheck.check("{path_label} costs {cost_5yr} over {horizon_years}.", FACTS) == []


def test_words_that_merely_contain_a_number_word_are_fine():
    assert numcheck.check("Someone sensible tends to stone and money.", FACTS) == []


def test_render_substitutes_the_engines_exact_values():
    facts = {"path_label": "Buy out", "cost_5yr": "$31,200"}
    assert numcheck.verify_and_render("{path_label} costs {cost_5yr}.", facts) == "Buy out costs $31,200."


def test_verify_and_render_returns_none_for_bad_text():
    assert numcheck.verify_and_render("It costs 5 dollars.", {"a": "b"}) is None


def test_units_come_from_the_engine_with_correct_singular_and_plural():
    assert fmt_years(1) == "1 year"
    assert fmt_years(3) == "3 years"
    assert fmt_miles(13200) == "13,200 miles"
    assert fmt_miles(1) == "1 mile"
    assert fmt_rate(D("6.50")) == "6.5%"
    assert fmt_rate(D("7.00")) == "7%"
    assert fmt_rate(D("10")) == "10%"


def test_facts_values_include_their_units(make_lease, cfg):
    inp = make_lease(years_to_keep=1)
    facts, _ = build_facts(inp, evaluate(inp, cfg), cfg)
    assert facts["years_to_keep"] == "1 year"
    assert facts["horizon_years"] == "5 years"
    assert facts["miles_per_year"] == "13,200 miles"
    assert facts["financing_rate"] == "6.5%"
    assert facts["monthly_budget"] == "$2,250"
    facts3, _ = build_facts(make_lease(years_to_keep=3), evaluate(make_lease(years_to_keep=3), cfg), cfg)
    assert facts3["years_to_keep"] == "3 years"


def test_every_template_variant_passes_the_check():
    for variant in template.BODIES:
        assert numcheck.check(template.BODIES[variant], FACTS) == [], variant
        assert numcheck.check(template.HEADLINES[variant], FACTS) == [], variant
    flip_keys = {"flip_input", "flip_current", "flip_threshold", "flip_to_path"}
    assert numcheck.check(template.FLIP_SENTENCE, flip_keys) == []


def test_the_template_renders_for_lease_and_loan_in_every_variant(make_lease, make_loan, cfg):
    cases = [
        make_lease(),
        make_loan(),
        make_lease(cash=D(1000)),  # nothing fits
        make_loan(monthly_budget=D(450)),  # only the cheaper loan paths fit
    ]
    for inp in cases:
        facts, variant = build_facts(inp, evaluate(inp, cfg), cfg)
        body = template.render_checked(template.BODIES[variant], facts)
        head = template.render_checked(template.HEADLINES[variant], facts)
        assert body and head, variant
        assert "{" not in body and "{" not in head


def test_a_flip_sentence_is_rendered_in_the_backend_with_units(make_lease):
    flip = Flip(
        input="miles_per_year", current=D(13200), threshold=D(15800),
        to_path="return_lease_new", relative_change=D("0.197"),
    )
    assert template.flip_sentence(flip_facts(flip, "lease")) == (
        "If your miles per year changed from 13,200 miles to 15,800 miles, "
        "Return and lease new would become the recommendation."
    )


def test_every_flip_sentence_for_real_customers_passes_the_check(make_lease, make_loan, cfg):
    for inp in (make_lease(), make_loan()):
        for f in find_flips(inp, cfg):
            assert template.flip_sentence(flip_facts(f, inp.customer.contract.type)) is not None


def test_vague_plural_quantities_count_as_number_words_too():
    texts = (
        "You would save hundreds.", "Thousands in fees.", "Millions of options.", "A dozen reasons.", "Dozens of cars.",
    )
    for text in texts:
        assert numcheck.check(text, []), text
    assert not numcheck.check("You would save {savings_5yr}.", ["savings_5yr"])
