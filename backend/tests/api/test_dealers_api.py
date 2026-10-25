"""Nearby dealers and the next step (FR-014, FR-035). No network: the search is a fake built from the
captured SerpApi response."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crossroads.adapters.dealers import DealerLookupError, FakeDealers, parse_maps_results
from crossroads.config import Config
from crossroads.customer_api.main import create_app
from crossroads.customer_api.paths_service import assumptions_for, default_inputs
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

PROFILES = generate_profiles()
CAPTURED = json.loads((Path(__file__).parent.parent / "fixtures" / "serpapi_maps_toyota.json").read_text())


def make(dealers=None, **kw):
    """A fresh app and store (the dealer cache lives in the store), with the captured dealers by default."""
    dealers = FakeDealers(parse_maps_results(CAPTURED)) if dealers is None else dealers
    app = create_app(store=InMemoryStore(PROFILES), dealers=dealers, **kw)
    return TestClient(app, raise_server_exceptions=False), dealers


def step(client, cid, path, kind="primary"):
    return client.post(f"/api/customers/{cid}/next-step", json={"path": path, "kind": kind})


def test_the_three_nearest_dealers_come_back_nearest_first():
    client, _ = make()
    r = client.get("/api/customers/cust_01/dealers")
    assert r.status_code == 200
    found = r.json()["dealers"]
    assert len(found) == 3 and found[0]["name"] == "Toyota of Plano"
    assert set(found[0]) == {"name", "address", "hours", "rating", "distance_miles"}
    assert [d["distance_miles"] for d in found] == sorted(d["distance_miles"] for d in found)
    assert found[0]["hours"] == "Open · Closes 9 PM" and 4 <= found[0]["rating"] <= 5


def test_ranking_uses_the_customers_own_location():
    client, _ = make()
    near = client.get("/api/customers/cust_01/dealers").json()["dealers"][0]["distance_miles"]  # Plano
    far = client.get("/api/customers/cust_02/dealers").json()["dealers"][0]["distance_miles"]  # Phoenix
    assert near < 3 and far > 500


def test_lookups_are_cached_by_zip_so_the_screen_never_waits_on_a_live_search():
    client, fake = make()
    client.get("/api/customers/cust_01/dealers")
    client.get("/api/customers/cust_01/dealers")
    client.get("/api/customers/cust_07/dealers")  # a second customer in the same ZIP
    assert fake.calls == 1


def test_a_failed_lookup_is_a_readable_503_with_nothing_internal():
    class Down:
        def search(self, zip_code, lat, lng):
            raise DealerLookupError("secret internal detail https://serpapi.com/?api_key=KEY")

    client, _ = make(Down())
    r = client.get("/api/customers/cust_01/dealers")
    assert r.status_code == 503
    assert r.json() == {"detail": "Nearby dealers couldn't be loaded right now."}
    assert "KEY" not in r.text and "secret" not in r.text


def test_the_next_step_never_depends_on_the_dealer_lookup():
    class Down:
        def search(self, zip_code, lat, lng):
            raise DealerLookupError("down")

    client, _ = make(Down())
    assert client.get("/api/customers/cust_01/dealers").status_code == 503
    assert step(client, "cust_01", "buy_out").status_code == 200


def test_with_no_dealer_source_configured_it_is_a_readable_503():
    client = TestClient(create_app(store=InMemoryStore(PROFILES)), raise_server_exceptions=False)
    r = client.get("/api/customers/cust_01/dealers")
    assert r.status_code == 503 and "couldn't be loaded" in r.json()["detail"]


def test_an_empty_search_is_a_valid_empty_list():
    client, fake = make(FakeDealers([]))
    r = client.get("/api/customers/cust_01/dealers")
    assert r.status_code == 200 and r.json() == {"dealers": []}


def test_an_unknown_customer_is_a_readable_404():
    client, _ = make()
    assert client.get("/api/customers/nobody/dealers").status_code == 404
    assert step(client, "nobody", "buy_out").status_code == 404


def test_the_primary_next_step_confirms_the_chosen_path():
    client, _ = make()
    r = client.post("/api/customers/cust_01/next-step", json={"path": "buy_out", "kind": "primary"})
    assert r.status_code == 200
    assert r.json()["path_label"] == "Buy out"
    assert r.json()["confirmation"].startswith("You chose Buy out.") and "specialist" in r.json()["confirmation"]


def test_the_next_step_names_its_type_so_the_customer_knows_what_to_expect():
    client, _ = make()
    kinds = {}
    for path in ("buy_out", "walk_away"):  # cust_01 has a lease
        r = client.post("/api/customers/cust_01/next-step", json={"path": path, "kind": "primary"})
        kinds[path] = (r.json().get("step_type"), r.json().get("step_label"))
    assert kinds["buy_out"] == ("eligible_offer", "Eligible offer")
    assert kinds["walk_away"] == ("specialist_follow_up", "Specialist follow-up")
    r = client.post("/api/customers/cust_07/next-step", json={"path": "extra_principal", "kind": "primary"})
    assert (r.json()["step_type"], r.json()["step_label"]) == ("self_service", "Self-service")


def test_talk_to_a_specialist_is_its_own_confirmation():
    client, _ = make()
    r = client.post("/api/customers/cust_01/next-step", json={"path": "buy_out", "kind": "specialist"})
    assert "specialist will contact you" in r.json()["confirmation"]


def test_keeping_the_current_plan_is_confirmed_as_such():
    client, _ = make()
    r = client.post("/api/customers/cust_07/next-step", json={"path": "keep_as_is", "kind": "primary"})
    assert "staying on your current plan" in r.json()["confirmation"]


def test_a_path_from_the_other_contract_type_is_rejected():
    client, _ = make()
    assert step(client, "cust_01", "refinance").status_code == 422
    assert step(client, "cust_07", "buy_out").status_code == 422


def test_bad_requests_are_readable_errors():
    client, _ = make()
    r = client.post("/api/customers/cust_01/next-step", json={"path": "nonsense", "kind": "primary"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert client.post("/api/customers/cust_01/next-step", json={"path": "buy_out", "kind": "other"}).status_code == 422


def test_confirmations_contain_no_figures_so_there_is_nothing_to_mismatch():
    client, _ = make()
    for path in ("buy_out", "keep_as_is"):
        for kind in ("primary", "specialist"):
            text = step(client, "cust_01", path, kind).json()["confirmation"]
            assert not re.search(r"\d", text)


def test_the_next_step_is_stateless():
    client, _ = make()
    assert step(client, "cust_01", "buy_out").json() == step(client, "cust_01", "buy_out").json()


def test_the_paths_response_lists_its_illustrative_assumptions():
    client, _ = make()
    lease = client.post("/api/customers/cust_01/paths").json()["assumptions"]
    loan = client.post("/api/customers/cust_07/paths").json()["assumptions"]
    cfg = Config()
    assert any("$450 a month with $3,000 due at signing (illustrative)" in a for a in lease)  # an SUV
    assert any("$380 a month" in a for a in loan)  # a sedan
    assert any("12% of its value a year" in a and "$0.12" in a and "13,500" in a for a in lease)
    assert any("$395 disposition fee (illustrative)" in a for a in lease)
    assert any("financed over 60 months" in a for a in lease)
    assert any("extra principal adds $200 a month" in a and "illustrative" in a for a in loan)
    assert not any("disposition" in a for a in loan) and not any("extra principal" in a for a in lease)
    inp = default_inputs(InMemoryStore(PROFILES).get_record("cust_01"), cfg)
    assert assumptions_for(inp, cfg) == lease


@pytest.mark.parametrize("cid", [p.id for p in PROFILES])
def test_every_customer_has_assumptions_and_they_all_read_as_sentences(cid):
    client, _ = make()
    items = client.post(f"/api/customers/{cid}/paths").json()["assumptions"]
    assert len(items) >= 4 and all(a.endswith(".") for a in items)
