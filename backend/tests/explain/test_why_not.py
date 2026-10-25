"""The "Why not this one?" wording: fixed templates, engine figures, one reason in a fixed order."""

from __future__ import annotations

import re
from decimal import Decimal as D

import pytest

from crossroads.engine.schemas import PathOption, Shortfall
from crossroads.explain import numcheck, template
from crossroads.explain.why_not import why_not_line

HORIZON = "5 years"


def opt(path="refinance", cost="30000", *, eligible=True, reason=None, upfront="0", shortfalls=()):
    return PathOption(
        path=path, label=path, eligible=eligible, ineligible_reason=reason, five_year_cost=D(cost),
        monthly_payment=D("300"), upfront_cost=D(upfront), retained=True, revenue=D(0), cumulative_cost=[D(cost)],
        affordable=eligible and not shortfalls, shortfalls=list(shortfalls),
    )


def cash(amount):
    return Shortfall(kind="cash", amount=D(amount), text="x")


def monthly(amount):
    return Shortfall(kind="monthly", amount=D(amount), text="x")


REC = opt("buy_out", "27690")


def line(o, rec=REC):
    return why_not_line(o, rec, HORIZON)


def test_not_eligible_gives_the_engines_reason():
    o = opt(eligible=False, reason="Your current rate is already lower than this refinance rate.")
    assert line(o) == "Your current rate is already lower than this refinance rate."


def test_short_on_cash_up_front():
    assert line(opt(upfront="9000", shortfalls=[cash("1200.00")])) == "Needs $1,200 more cash upfront"


def test_short_on_cash_with_nothing_due_up_front_is_about_a_month_of_bills():
    text = line(opt(upfront="0", shortfalls=[cash("1200.00")]))
    assert text == "Needs $1,200 more in the bank to cover a month of bills"


def test_over_the_monthly_budget():
    assert line(opt(shortfalls=[monthly("84.60")])) == "Monthly payment is $85 over your budget"


def test_short_on_both():
    o = opt(upfront="9000", shortfalls=[monthly("84.60"), cash("1200.00")])
    assert line(o) == "Needs $1,200 more cash upfront and $85 more monthly budget"
    o = opt(upfront="0", shortfalls=[monthly("84.60"), cash("1200.00")])
    assert line(o) == "Needs $1,200 more for bills and $85 more monthly budget"


def test_affordable_but_dearer_costs_more():
    assert line(opt(cost="30000")) == "Costs $2,310 more over 5 years"


def test_a_tie_to_the_whole_dollar_costs_the_same():
    assert line(opt(cost="27690")) == "Costs the same over 5 years"


def test_the_recommended_path_has_no_line():
    assert line(REC) is None


def test_reasons_come_in_a_fixed_order():
    # not eligible beats unaffordable beats dearer
    both = opt(eligible=False, reason="Not available to you.", shortfalls=[cash("500")], cost="40000")
    assert line(both) == "Not available to you."
    assert line(opt(shortfalls=[cash("500")], upfront="900", cost="40000")) == "Needs $500 more cash upfront"


def test_an_unaffordable_path_that_is_cheaper_never_says_costs_more():
    cheaper = opt(cost="20000", upfront="9000", shortfalls=[cash("1200")])
    assert line(cheaper) == "Needs $1,200 more cash upfront"
    assert "Costs" not in line(cheaper)


def test_with_no_recommendation_nothing_compares_costs():
    assert line(opt(upfront="9000", shortfalls=[cash("1200")]), None) == "Needs $1,200 more cash upfront"
    assert line(opt(eligible=False, reason="Not available to you."), None) == "Not available to you."
    assert line(opt(cost="30000"), None) is None  # affordable with nothing to compare against: no line


def test_a_cheaper_affordable_path_gets_no_line_rather_than_a_wrong_one():
    assert line(opt(cost="20000")) is None


@pytest.mark.parametrize(
    "o",
    [
        opt(upfront="9000", shortfalls=[cash("1200.00")]),
        opt(upfront="0", shortfalls=[cash("1200.00")]),
        opt(shortfalls=[monthly("84.60")]),
        opt(upfront="9000", shortfalls=[monthly("84.60"), cash("1200.00")]),
        opt(upfront="0", shortfalls=[monthly("84.60"), cash("1200.00")]),
        opt(cost="30000"),
        opt(cost="27690"),
    ],
)
def test_every_line_is_short_plain_and_never_negative(o):
    text = line(o)
    assert text and "-" not in text and "$0 " not in text and not text.endswith("$0")
    words = [w for w in text.split() if not w.startswith("$")]
    assert len(words) + len([w for w in text.split() if w.startswith("$")]) <= 12
    assert len(re.findall(r"[.!?]", text.rstrip("."))) == 0  # one sentence


def test_the_same_inputs_give_the_same_line():
    o = opt(upfront="9000", shortfalls=[monthly("84.60"), cash("1200.00")])
    assert line(o) == line(o)


# --- the templates pass the number check ---------------------------------------------------------------

FACT_KEYS = {"ineligible_reason", "cash_gap", "monthly_gap", "cost_gap", "horizon_years"}


@pytest.mark.parametrize("name", sorted(template.WHY_NOT))
def test_every_template_passes_the_number_check(name):
    assert numcheck.check(template.WHY_NOT[name], FACT_KEYS) == []


def test_a_template_with_a_digit_or_number_word_or_unknown_placeholder_is_rejected():
    assert numcheck.check("Costs $5 more over {horizon_years}", FACT_KEYS)
    assert numcheck.check("Costs {cost_gap} more over five years", FACT_KEYS)
    assert numcheck.check("Costs {nope} more", FACT_KEYS)


def test_a_line_whose_template_fails_the_check_is_dropped(monkeypatch):
    monkeypatch.setitem(template.WHY_NOT, "more", "Costs {cost_gap} more over 5 years")
    assert line(opt(cost="30000")) is None


def test_no_template_is_longer_than_twelve_words():
    for name, text in template.WHY_NOT.items():
        words = text.replace("{", "").replace("}", "").split()  # a placeholder (a figure) counts as one word
        assert len(words) <= 12, (name, len(words))
