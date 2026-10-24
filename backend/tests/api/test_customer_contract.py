"""The customer API's contract: what it exposes, and what it never does (FR-023, FR-024, FR-028, SC-008, SC-010)."""

import ast
import json
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

import crossroads.customer_api as customer_api_pkg
from crossroads.customer_api.main import create_app
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

PROFILES = generate_profiles()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(store=InMemoryStore(PROFILES)))


def test_the_picker_list_has_only_id_name_and_vehicle_label_for_everyone(client):
    rows = client.get("/api/customers").json()
    assert len(rows) == 12
    for row in rows:
        assert set(row) == {"id", "display_name", "vehicle_label"}
        assert all(isinstance(v, str) and v for v in row.values())


def test_the_picker_list_carries_no_financial_or_contract_detail(client):
    raw = client.get("/api/customers").text.lower()
    for word in ("balance", "payment", "income", "residual", "apr", "bills", "checking", "savings", "odometer"):
        assert word not in raw, word


def test_vehicle_labels_read_like_the_wireframe(client):
    by_id = {r["id"]: r["vehicle_label"] for r in client.get("/api/customers").json()}
    assert by_id["cust_01"] == "RAV4 lease"
    assert by_id["cust_07"] == "Camry loan"


def test_the_api_exposes_only_customer_routes(client):
    paths = set(client.get("/api/openapi.json").json()["paths"])
    assert paths == {"/api/customers", "/api/customers/{customer_id}/overview",
                     "/api/customers/{customer_id}/spending", "/api/customers/{customer_id}/paths",
                     "/api/customers/{customer_id}/explanation", "/api/customers/{customer_id}/dealers",
                     "/api/customers/{customer_id}/next-step", "/healthz"}
    for path in paths:
        for word in ("internal", "portfolio", "aggregate", "retained", "revenue", "business"):
            assert word not in path


def test_customer_code_never_imports_the_internal_api():
    package = Path(customer_api_pkg.__file__).parent
    for source in package.glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not any("internal_api" in n for n in names), f"{source.name} imports internal_api"


def test_an_overview_contains_only_the_selected_customers_data(client):
    body = client.get("/api/customers/cust_01/overview").text
    for other in PROFILES:
        if other.id != "cust_01":
            assert other.display_name not in body and other.id not in body
    assert "cust_01" in body


def test_spending_contains_only_the_selected_customers_data(client):
    body = client.get("/api/customers/cust_02/spending").text
    assert "cust_" not in body


def test_an_unknown_customer_is_a_readable_404(client):
    for suffix in ("overview", "spending"):
        r = client.get(f"/api/customers/nobody/{suffix}")
        assert r.status_code == 404
        assert "couldn't find" in r.json()["detail"]


def test_there_is_no_route_for_another_customers_list_or_an_aggregate(client):
    for path in ("/api/portfolio", "/api/internal/portfolio", "/api/customers/summary", "/api/aggregate"):
        assert client.get(path).status_code == 404


class BrokenStore:
    def list_customers(self):
        raise psycopg.OperationalError("connection to server at db failed: password=hunter2")

    def get_record(self, customer_id):
        raise psycopg.OperationalError("connection to server at db failed: password=hunter2")

    def monthly_miles(self, customer_id):
        raise psycopg.OperationalError("boom")

    def monthly_spend(self, customer_id):
        raise psycopg.OperationalError("boom")


def test_a_database_outage_gives_a_readable_503_with_no_internals():
    broken = TestClient(create_app(store=BrokenStore()), raise_server_exceptions=False)
    for path in ("/api/customers", "/api/customers/cust_01/overview", "/api/customers/cust_01/spending"):
        r = broken.get(path)
        assert r.status_code == 503
        assert "temporarily unavailable" in r.json()["detail"]
        assert "hunter2" not in r.text and "Traceback" not in r.text


def test_healthz_answers(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_every_response_is_valid_json_with_money_as_strings(client):
    data = json.loads(client.get("/api/customers/cust_01/overview").text)
    assert data["tiles"]["monthly_payment"] == "389.00"
    assert isinstance(data["money"]["checking"], str)
