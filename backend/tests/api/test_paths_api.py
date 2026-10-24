"""The paths and explanation routes (US2, FR-006..FR-014, FR-021, SC-003, SC-004)."""

import re
import time
from decimal import ROUND_HALF_UP
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from crossroads.adapters.llm import ExplanationDraft, FakeLLM
from crossroads.config import Config
from crossroads.customer_api.main import create_app
from crossroads.customer_api.paths_service import default_inputs
from crossroads.engine.money import fmt_money
from crossroads.engine.recommend import evaluate
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

PROFILES = generate_profiles()
STORE = InMemoryStore(PROFILES)
CFG = Config()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(store=STORE))


def paths(client, cid, body=None):
    url = f"/api/customers/{cid}/paths"
    r = client.post(url, json=body) if body is not None else client.post(url)
    assert r.status_code == 200, r.text
    return r.json()


def test_no_body_and_an_empty_body_both_give_the_customers_defaults(client):
    a, b = paths(client, "cust_01"), paths(client, "cust_01", {})
    assert a == b
    used = a["inputs_used"]
    assert used["monthly_budget"] == "2250"  # income − bills − the $300 buffer
    assert used["years_to_keep"] == 2 and used["financing_rate"] == "6.5"
    assert used["miles_per_year"] % 100 == 0


def test_a_lease_and_a_loan_each_get_four_paths_with_keep_as_is_first(client):
    lease, loan = paths(client, "cust_01"), paths(client, "cust_07")
    assert [o["path"] for o in lease["options"]] == ["keep_as_is", "buy_out", "return_lease_new", "walk_away"]
    assert [o["path"] for o in loan["options"]] == ["keep_as_is", "trade_in_early", "refinance", "extra_principal"]
    assert (lease["contract_type"], loan["contract_type"]) == ("lease", "loan")


def test_every_option_has_all_three_measures_and_a_sixty_month_cost_line(client):
    for cid in (p.id for p in PROFILES):
        for o in paths(client, cid)["options"]:
            assert D(o["five_year_cost"]) == D(o["five_year_cost"]).to_integral_value()
            assert o["monthly_payment"] and o["upfront_cost"] and o["tradeoff"]
            assert len(o["cumulative_cost"]) == 60
            # the engine rounds half up (FR-033); Python's round() would round half to even
            assert D(o["cumulative_cost"][-1]).quantize(D(1), ROUND_HALF_UP) == D(o["five_year_cost"])


def test_the_response_matches_the_engine(client):
    for cid in ("cust_01", "cust_07", "cust_03", "cust_10"):
        inp = default_inputs(STORE.get_record(cid), CFG)
        ev = evaluate(inp, CFG)
        got = paths(client, cid)
        assert got["recommendation"]["path"] == ev.recommendation.path
        assert {o["path"]: o["five_year_cost"] for o in got["options"]} == {
            o.path: str(o.five_year_cost) for o in ev.options
        }


def test_an_unaffordable_option_stays_visible_with_the_exact_shortfall(client):
    lease = paths(client, "cust_01")
    option = next(o for o in lease["options"] if o["path"] == "return_lease_new")
    assert not option["affordable"] and option["eligible"]
    # 4,900 cash − 2,650 bills = 2,250 available against 7,296 due up front
    assert option["shortfalls"] == [{"kind": "cash", "amount": "5046.00", "text": "needs $5,046 more cash upfront"}]
    assert lease["recommendation"]["path"] != "return_lease_new"


def test_an_ineligible_option_carries_its_reason_and_is_never_recommended(client):
    loan = paths(client, "cust_08")  # a 3.4% loan: a 6.5% refinance would be worse
    refinance = next(o for o in loan["options"] if o["path"] == "refinance")
    assert not refinance["eligible"] and refinance["ineligible_reason"]
    assert loan["recommendation"]["path"] != "refinance"


def test_nothing_affordable_says_so_and_names_the_closest_path(client):
    data = paths(client, "cust_04")  # cash-poor
    rec = data["recommendation"]
    assert rec["path"] is None and rec["closest_when_none"] and D(rec["closest_gap"]) > 0
    assert "None of your paths fit" in rec["explanation"]["text"]
    assert rec["explanation"]["verified"] is True


def test_changing_an_input_changes_the_results(client):
    base = paths(client, "cust_01")
    squeezed = paths(client, "cust_01", {"monthly_budget": 400})
    assert base["recommendation"]["path"] == "buy_out"
    assert squeezed["recommendation"]["path"] == "keep_as_is"  # buy out's payment is over 400
    assert squeezed["inputs_used"]["monthly_budget"] == "400"
    assert base["options"] != squeezed["options"]
    more_miles = paths(client, "cust_01", {"miles_per_year": 20000})
    assert more_miles["options"] != base["options"]


def test_flips_are_one_per_input_sorted_and_name_a_different_path(client):
    for cid in ("cust_01", "cust_07", "cust_10"):
        data = paths(client, cid)
        flips = data["flips"]
        assert len({f["input"] for f in flips}) == len(flips)
        changes = [D(f["relative_change"]) for f in flips]
        assert changes == sorted(changes)
        assert all(f["to_path"] != data["recommendation"]["path"] for f in flips)
        assert all(f["text"].startswith("If ") and "would become the recommendation" in f["text"] for f in flips)


def test_the_slider_ranges_are_reported_with_the_customers_own_budget_maximum(client):
    ranges = paths(client, "cust_01")["ranges"]
    assert ranges["miles_per_year"] == {"min": "5000", "max": "25000", "step": "100"}
    assert ranges["years_to_keep"] == {"min": "1", "max": "8", "step": "1"}
    assert ranges["financing_rate"] == {"min": "3", "max": "12", "step": "0.25"}
    assert ranges["monthly_budget"] == {"min": "200", "max": "2250", "step": "10"}  # raised to the default
    # cust_02's own default is 1,500, also above the standard 1,200; a customer below it keeps 1,200
    assert paths(client, "cust_02")["ranges"]["monthly_budget"]["max"] == "1500"
    low = next(p.id for p in PROFILES if D(paths(client, p.id)["inputs_used"]["monthly_budget"]) <= 1200)
    assert paths(client, low)["ranges"]["monthly_budget"]["max"] == "1200"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"miles_per_year": 4000}, "Miles per year"),
        ({"miles_per_year": 12345}, "Miles per year"),
        ({"miles_per_year": 30000}, "Miles per year"),
        ({"monthly_budget": 100}, "Monthly budget"),
        ({"monthly_budget": 205}, "Monthly budget"),
        ({"years_to_keep": 0}, "Years you plan to keep a car"),
        ({"years_to_keep": 9}, "Years you plan to keep a car"),
        ({"financing_rate": 2}, "Financing rate"),
        ({"financing_rate": 6.3}, "Financing rate"),
    ],
)
def test_out_of_range_inputs_are_rejected_with_a_readable_message(client, body, field):
    r = client.post("/api/customers/cust_01/paths", json=body)
    assert r.status_code == 422
    assert r.json()["detail"].startswith(field)
    assert r.json()["errors"][0]["field"] == next(iter(body))


def test_a_budget_above_the_customers_own_maximum_is_rejected(client):
    r = client.post("/api/customers/cust_01/paths", json={"monthly_budget": 2260})
    assert r.status_code == 422 and "at most $2,250" in r.json()["detail"]
    assert client.post("/api/customers/cust_01/paths", json={"monthly_budget": 2250}).status_code == 200


def test_a_rejected_request_changes_nothing(client):
    before = paths(client, "cust_01")
    client.post("/api/customers/cust_01/paths", json={"miles_per_year": 4000})
    assert paths(client, "cust_01") == before


def test_unknown_customer_is_a_readable_404(client):
    for route in ("paths", "explanation"):
        r = client.post(f"/api/customers/nobody/{route}")
        assert r.status_code == 404 and "couldn't find" in r.json()["detail"]


def _numbers(text: str) -> set[str]:
    # keeps "13,200" and "6.5" whole, and never swallows a sentence comma after a number
    return set(re.findall(r"\d+(?:[.,]\d+)*", text))


def _allowed_numbers(data: dict) -> set[str]:
    values = []
    for o in data["options"]:
        values += [o["five_year_cost"], o["monthly_payment"], o["upfront_cost"]]
    costs = [D(o["five_year_cost"]) for o in data["options"]]
    values += [a - b for a in costs for b in costs]
    values += [data["recommendation"]["monthly_room_left"], data["recommendation"]["closest_gap"]]
    values += [data["inputs_used"]["monthly_budget"]]
    return {fmt_money(v).lstrip("-$") for v in values} | {"5"}  # the fixed five-year horizon


def test_every_number_in_every_explanation_matches_a_computed_figure(client):
    for p in PROFILES:
        data = paths(client, p.id)
        text = data["recommendation"]["explanation"]["text"] + " " + data["recommendation"]["explanation"]["headline"]
        assert _numbers(text) <= _allowed_numbers(data), p.id
        for flip in data["flips"]:
            assert _numbers(flip["text"]) == _flip_numbers(flip), (p.id, flip["text"])


def _flip_numbers(flip: dict) -> set[str]:
    """The numbers a flip sentence may contain: only its own current and threshold, formatted by
    the rules for that input, worked out here independently of the backend's formatter."""
    out = set()
    for key in ("current", "threshold"):
        v = D(flip[key])
        if flip["input"] == "miles_per_year":
            out.add(f"{int(v):,}")
        elif flip["input"] == "monthly_budget":
            out.add(f"{int(v):,}")
        elif flip["input"] == "years_to_keep":
            out.add(str(int(v)))
        else:  # a rate: no trailing zeros
            out.add(format(v.normalize(), "f"))
    return out


def test_the_paths_response_is_fast_enough_for_live_sliders(client):
    # SC-004 targets 1 s; 2 s keeps the test from being flaky on a slow machine.
    for p in PROFILES:
        start = time.perf_counter()
        paths(client, p.id, {"miles_per_year": 15000})
        assert time.perf_counter() - start < 2.0, p.id


GOOD = ExplanationDraft(
    headline="{path_label} comes out ahead",
    explanation="{path_label} costs {cost_5yr} over {horizon_years}, {savings_5yr} less than {compare_label}.",
)
BAD = ExplanationDraft(headline="Save 5000", explanation="It costs 31,200 over 5 years.")


def explanation(llm, cid="cust_01", body=None):
    c = TestClient(create_app(store=STORE, llm=llm))
    r = c.post(f"/api/customers/{cid}/explanation", json=body or {})
    assert r.status_code == 200, r.text
    return r.json(), paths(c, cid, body or {})


def test_the_model_text_is_returned_with_the_engines_own_figures():
    e, data = explanation(FakeLLM([GOOD]))
    assert (e["source"], e["verified"]) == ("gemini", True)
    best = next(o for o in data["options"] if o["path"] == data["recommendation"]["path"])
    assert fmt_money(best["five_year_cost"]) in e["text"]
    assert "{" not in e["text"]


def test_model_text_with_its_own_numbers_is_replaced_by_the_checked_template():
    e, data = explanation(FakeLLM([BAD, BAD]))
    assert (e["source"], e["verified"]) == ("template", True)
    assert e["text"] == data["recommendation"]["explanation"]["text"]


def test_without_a_model_the_explanation_route_returns_the_template():
    e, data = explanation(None)
    assert e["source"] == "template" and e == data["recommendation"]["explanation"]


def test_the_paths_route_never_waits_for_the_model():
    llm = FakeLLM([GOOD])
    c = TestClient(create_app(store=STORE, llm=llm))
    c.post("/api/customers/cust_01/paths")
    assert llm.prompts == []
