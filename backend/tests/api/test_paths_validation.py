"""Input validation on the paths route: every slider is range- and step-checked, with a readable
message, and a rejected request changes nothing (FR-012, FR-013)."""

import pytest
from fastapi.testclient import TestClient

from crossroads.customer_api.main import create_app
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

PROFILES = generate_profiles()
URL = "/api/customers/cust_01/paths"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(store=InMemoryStore(PROFILES)))


@pytest.mark.parametrize(
    "body",
    [
        {"miles_per_year": 5000}, {"miles_per_year": 25000},
        {"years_to_keep": 1}, {"years_to_keep": 8},
        {"financing_rate": 3}, {"financing_rate": 12}, {"financing_rate": 6.25},
        {"monthly_budget": 200}, {"monthly_budget": 2250},
    ],
)
def test_values_at_the_edge_of_each_range_are_accepted(client, body):
    assert client.post(URL, json=body).status_code == 200


@pytest.mark.parametrize(
    ("body", "label"),
    [
        ({"miles_per_year": 4900}, "Miles per year"),
        ({"miles_per_year": 25100}, "Miles per year"),
        ({"miles_per_year": 12350}, "Miles per year"),
        ({"years_to_keep": 0}, "Years you plan to keep a car"),
        ({"years_to_keep": 9}, "Years you plan to keep a car"),
        ({"financing_rate": 2.75}, "Financing rate"),
        ({"financing_rate": 12.25}, "Financing rate"),
        ({"financing_rate": 6.1}, "Financing rate"),
        ({"monthly_budget": 190}, "Monthly budget"),
        ({"monthly_budget": 1255}, "Monthly budget"),
        ({"monthly_budget": 2260}, "Monthly budget"),  # above this customer's own maximum
    ],
)
def test_each_out_of_range_input_gets_a_message_naming_the_input(client, body, label):
    r = client.post(URL, json=body)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and r.json()["detail"].startswith(label)


def test_several_bad_inputs_are_all_reported(client):
    r = client.post(URL, json={"miles_per_year": 100, "years_to_keep": 20})
    detail = r.json()["detail"]
    assert "Miles per year" in detail and "Years you plan to keep a car" in detail
    assert {e["field"] for e in r.json()["errors"]} == {"miles_per_year", "years_to_keep"}


def test_text_where_a_number_belongs_is_a_readable_error(client):
    r = client.post(URL, json={"miles_per_year": "lots"})
    assert r.status_code == 422 and r.json()["detail"].startswith("Miles per year")
    assert "Traceback" not in r.text


def test_a_rejected_request_changes_nothing(client):
    before = client.post(URL).json()
    for bad in ({"miles_per_year": 4900}, {"monthly_budget": 99999}, {"years_to_keep": 0}):
        assert client.post(URL, json=bad).status_code == 422
    assert client.post(URL).json() == before


def test_the_budget_maximum_is_per_customer(client):
    # cust_01's own default is 2,250; a customer whose default is under 1,200 keeps the standard maximum
    assert client.post(URL, json={"monthly_budget": 2250}).status_code == 200
    low = next(
        p.id
        for p in PROFILES
        if client.post(f"/api/customers/{p.id}/paths").json()["ranges"]["monthly_budget"]["max"] == "1200"
    )
    assert client.post(f"/api/customers/{low}/paths", json={"monthly_budget": 1210}).status_code == 422
    assert client.post(f"/api/customers/{low}/paths", json={"monthly_budget": 1200}).status_code == 200
