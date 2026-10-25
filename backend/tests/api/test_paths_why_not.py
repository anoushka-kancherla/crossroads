"""The "why_not" line on each option of the paths response (FR-001..FR-011, SC-001, SC-002, SC-004, SC-005)."""

import re
from decimal import ROUND_HALF_UP
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from crossroads.config import Config
from crossroads.customer_api.main import create_app
from crossroads.explain import template
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

STORE = InMemoryStore(generate_profiles())
IDS = [f"cust_{i:02d}" for i in range(1, 13)]
SETTINGS = [None, {"monthly_budget": "600"}, {"years_to_keep": 5, "miles_per_year": 20000}, {"monthly_budget": "1000"}]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(store=STORE, cfg=Config()))


def paths(client, cid, body=None):
    r = client.post(f"/api/customers/{cid}/paths", json=body or {})
    assert r.status_code == 200, r.text
    return r.json()


def money(x) -> str:
    v = int(D(str(x)).quantize(D(1), ROUND_HALF_UP))
    return f"-${-v:,}" if v < 0 else f"${v:,}"


def expected(opt, rec):
    """The line worked out independently from the response's own figures."""
    if rec is not None and opt["path"] == rec["path"]:
        return None
    if not opt["eligible"]:
        return opt["ineligible_reason"]
    if opt["shortfalls"]:
        by = {s["kind"]: money(s["amount"]) for s in opt["shortfalls"]}
        bills = D(opt["upfront_cost"]) <= 0
        if "cash" in by and "monthly" in by:
            what = "for bills" if bills else "cash upfront"
            return f"Needs {by['cash']} more {what} and {by['monthly']} more monthly budget"
        if "cash" in by:
            what = "in the bank to cover a month of bills" if bills else "cash upfront"
            return f"Needs {by['cash']} more {what}"
        return f"Monthly payment is {by['monthly']} over your budget"
    if rec is None:
        return None
    diff = D(opt["five_year_cost"]) - D(rec["five_year_cost"])
    if diff < 0:
        return None
    return "Costs the same over 5 years" if diff == 0 else f"Costs {money(diff)} more over 5 years"


def test_the_recommended_path_has_no_line_and_every_other_has_exactly_one(client):
    r = paths(client, "cust_01")
    rec = r["recommendation"]["path"]
    assert rec is not None
    for o in r["options"]:
        if o["path"] == rec:
            assert o["why_not"] is None
        else:
            assert isinstance(o["why_not"], str) and o["why_not"]


def test_a_dearer_affordable_path_says_how_much_more_it_costs(client):
    r = paths(client, "cust_01")
    rec = next(o for o in r["options"] if o["path"] == r["recommendation"]["path"])
    dearer = [o for o in r["options"] if o["affordable"] and o["path"] != rec["path"]]
    assert dearer, "the demo customer has an affordable alternative"
    for o in dearer:
        diff = D(o["five_year_cost"]) - D(rec["five_year_cost"])
        assert o["why_not"] == f"Costs {money(diff)} more over 5 years"


def test_an_unaffordable_path_names_its_own_shortfall(client):
    r = paths(client, "cust_01")
    short = [o for o in r["options"] if o["eligible"] and not o["affordable"]]
    assert short
    for o in short:
        for s in o["shortfalls"]:
            assert money(s["amount"]) in o["why_not"]


@pytest.mark.parametrize("cid", IDS)
@pytest.mark.parametrize("body", SETTINGS)
def test_every_line_matches_an_independent_recomputation(client, cid, body):
    r = paths(client, cid, body)
    rec_path = r["recommendation"]["path"]
    rec = next((o for o in r["options"] if o["path"] == rec_path), None)
    for o in r["options"]:
        assert o["why_not"] == expected(o, rec), (cid, body, o["path"])
        if o["why_not"]:
            assert "-" not in o["why_not"] and "$0 more" not in o["why_not"]
            assert len(re.findall(r"\$[\d,]+", o["why_not"])) <= 2


def test_the_same_request_gives_the_same_lines(client):
    a, b = paths(client, "cust_07"), paths(client, "cust_07")
    assert [o["why_not"] for o in a["options"]] == [o["why_not"] for o in b["options"]]


@pytest.mark.parametrize("cid", ["cust_04", "cust_11"])
def test_with_no_recommendation_every_path_says_what_it_is_missing(client, cid):
    r = paths(client, cid)
    assert r["recommendation"]["path"] is None
    for o in r["options"]:
        assert o["why_not"], o["path"]
        assert "Costs" not in o["why_not"]


def test_a_line_that_fails_the_number_check_is_dropped_alone(client, monkeypatch):
    good = paths(client, "cust_01")
    monkeypatch.setitem(template.WHY_NOT, "more", "Costs {cost_gap} more over 5 years")
    bad = paths(client, "cust_01")
    for g, b in zip(good["options"], bad["options"], strict=True):
        assert {k: v for k, v in g.items() if k != "why_not"} == {k: v for k, v in b.items() if k != "why_not"}
        if g["why_not"] and g["why_not"].startswith("Costs"):
            assert b["why_not"] is None
        else:
            assert b["why_not"] == g["why_not"]
