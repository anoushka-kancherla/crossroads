"""Pressing the main button on a path records one acceptance; nothing else does (FR-001..FR-003, FR-007)."""

from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from crossroads.config import Config
from crossroads.customer_api.main import create_app
from crossroads.customer_api.paths_service import apply_request, default_inputs
from crossroads.customer_api.schemas import PathsRequest
from crossroads.engine.recommend import evaluate
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

CFG = Config()
PROFILES = generate_profiles()


def make(store=None):
    store = store or InMemoryStore(PROFILES)
    return store, TestClient(create_app(store=store, cfg=CFG))


def post(client, cid, body):
    return client.post(f"/api/customers/{cid}/next-step", json=body)


def option_for(store, cid, path, inputs=None):
    rec = store.get_record(cid)
    base = default_inputs(rec, CFG)
    inp = apply_request(base, PathsRequest(**inputs)) if inputs else base
    return next(o for o in evaluate(inp, CFG).options if o.path == path)


def recommended(client, cid):
    r = client.post(f"/api/customers/{cid}/paths", json={}).json()
    return r["recommendation"]["path"]


def test_a_primary_press_records_one_entry_with_the_engines_own_figures():
    store, client = make()
    path = recommended(client, "cust_01")
    r = post(client, "cust_01", {"path": path, "kind": "primary"})
    assert r.status_code == 200
    assert set(r.json()) == {"path_label", "confirmation", "step_type", "step_label"}  # the response is unchanged
    [e] = store.latest_acceptances()
    opt = option_for(store, "cust_01", path)
    assert (e.customer_id, e.path, e.retained, e.revenue) == ("cust_01", path, opt.retained, opt.revenue)
    assert store.acceptance_count() == 1


def test_the_slider_settings_in_the_request_are_the_ones_the_entry_uses():
    store, client = make()
    inputs = {"miles_per_year": 20000, "years_to_keep": 4}
    post(client, "cust_01", {"path": "buy_out", "kind": "primary", "inputs": inputs})
    [e] = store.latest_acceptances()
    assert e.revenue == option_for(store, "cust_01", "buy_out", inputs).revenue


def test_a_path_that_is_not_the_current_recommendation_still_records_its_own_figures():
    store, client = make()
    other = next(p for p in ("keep_as_is", "walk_away") if p != recommended(client, "cust_01"))
    post(client, "cust_01", {"path": other, "kind": "primary"})
    [e] = store.latest_acceptances()
    opt = option_for(store, "cust_01", other)
    assert (e.path, e.retained, e.revenue) == (other, opt.retained, opt.revenue)


def test_walking_away_is_recorded_as_not_retained_with_no_income():
    store, client = make()
    post(client, "cust_01", {"path": "walk_away", "kind": "primary"})
    [e] = store.latest_acceptances()
    assert e.retained is False and e.revenue == D(0)


def test_talking_to_a_specialist_records_nothing():
    store, client = make()
    r = post(client, "cust_01", {"path": "buy_out", "kind": "specialist"})
    assert r.status_code == 200 and store.acceptance_count() == 0


def test_a_path_that_is_not_one_of_the_options_is_refused_and_records_nothing():
    store, client = make()
    r = post(client, "cust_01", {"path": "refinance", "kind": "primary"})  # a loan path, and cust_01 has a lease
    assert r.status_code == 422 and store.acceptance_count() == 0


def test_an_unknown_customer_is_refused_and_records_nothing():
    store, client = make()
    assert post(client, "cust_99", {"path": "buy_out", "kind": "primary"}).status_code == 404
    assert store.acceptance_count() == 0


def test_pressing_twice_records_two_entries_and_counts_the_customer_once():
    store, client = make()
    post(client, "cust_01", {"path": "buy_out", "kind": "primary"})
    post(client, "cust_01", {"path": "keep_as_is", "kind": "primary"})
    assert store.acceptance_count() == 2 and len(store.latest_acceptances()) == 1


def test_a_failed_write_never_reaches_the_customer():
    class Failing(InMemoryStore):
        def record_acceptance(self, entry):
            raise RuntimeError("the log is unavailable")

    good_store, good = make()
    bad_store, bad = make(Failing(PROFILES))
    body = {"path": "buy_out", "kind": "primary"}
    a, b = post(good, "cust_01", body), post(bad, "cust_01", body)
    assert b.status_code == 200 and b.json() == a.json()
    assert "unavailable" not in b.text and bad_store.acceptance_count() == 0


def test_the_log_holds_only_the_five_fields():
    store, client = make()
    post(client, "cust_01", {"path": "buy_out", "kind": "primary"})
    [e] = store.latest_acceptances()
    assert set(vars(e)) == {"customer_id", "path", "retained", "revenue", "ts"}


@pytest.mark.parametrize("bad", [{"miles_per_year": 100}, {"monthly_budget": "5"}])
def test_slider_values_outside_their_limits_are_refused_as_before(bad):
    store, client = make()
    r = post(client, "cust_01", {"path": "buy_out", "kind": "primary", "inputs": bad})
    assert r.status_code == 422 and store.acceptance_count() == 0
