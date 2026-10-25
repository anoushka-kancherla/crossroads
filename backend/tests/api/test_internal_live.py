"""GET /api/internal/live: the staff dashboard's live acceptance figures (FR-004, FR-006, FR-009..FR-014)."""

import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from crossroads.config import Config, Settings
from crossroads.customer_api.main import create_app as customer_app
from crossroads.customer_api.store import Acceptance
from crossroads.internal_api.auth import hash_password
from crossroads.internal_api.main import create_app as staff_app
from crossroads.internal_api.snapshots import InMemorySnapshots
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

URL = "/api/internal"
PASSWORD = secrets.token_urlsafe(18)  # fresh each run, never written to a file
SETTINGS = Settings("", "", "", "", "", "staff", hash_password(PASSWORD), secrets.token_urlsafe(32))
PROFILES = generate_profiles()
T0 = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def acc(cid, path="buy_out", n=0, retained=True, revenue="1000.00"):
    return Acceptance(cid, path, retained, D(revenue), T0 + timedelta(seconds=n))


def staff(store, *, signed_in=True):
    app = staff_app(settings=SETTINGS, store=store, snapshots=InMemorySnapshots())
    c = TestClient(app)
    if signed_in:
        assert c.post(f"{URL}/login", json={"username": "staff", "password": PASSWORD}).status_code == 204
    return c


def test_no_session_means_401_and_no_figures():
    r = staff(InMemoryStore(PROFILES), signed_in=False).get(f"{URL}/live")
    assert r.status_code == 401 and r.json() == {"detail": "Please sign in."}


def test_with_nothing_accepted_the_figures_say_so():
    d = staff(InMemoryStore(PROFILES)).get(f"{URL}/live").json()
    assert d["accepted_customers"] == 0 and d["customers_total"] == 12 and d["retained_customers"] == 0
    assert d["retained_pct"] is None and d["revenue_total"] == "0" and d["sequence"] == 0
    assert d["updated_at"]


def test_three_customers_two_retained():
    store = InMemoryStore(PROFILES)
    store.record_acceptance(acc("cust_01", revenue="3572.92"))
    store.record_acceptance(acc("cust_02", revenue="7212.23", n=1))
    store.record_acceptance(acc("cust_03", "walk_away", 2, False, "0.00"))
    d = staff(store).get(f"{URL}/live").json()
    assert (d["accepted_customers"], d["retained_customers"], d["retained_pct"]) == (3, 2, "67")
    assert d["revenue_total"] == "10785" and d["sequence"] == 3


def test_a_second_acceptance_by_one_customer_counts_the_customer_once_by_the_latest():
    store = InMemoryStore(PROFILES)
    store.record_acceptance(acc("cust_01", revenue="1000.00"))
    store.record_acceptance(acc("cust_01", "walk_away", 5, False, "0.00"))
    d = staff(store).get(f"{URL}/live").json()
    assert (d["accepted_customers"], d["retained_customers"], d["revenue_total"], d["sequence"]) == (1, 0, "0", 2)


def test_the_response_has_no_customer_or_path():
    store = InMemoryStore(PROFILES)
    store.record_acceptance(acc("cust_01"))
    text = staff(store).get(f"{URL}/live").text
    assert "cust_" not in text and "buy_out" not in text


def test_an_acceptance_made_on_the_customer_app_shows_up_on_the_next_request():
    store = InMemoryStore(PROFILES)
    customer = TestClient(customer_app(store=store, cfg=Config()))
    dash = staff(store)
    assert dash.get(f"{URL}/live").json()["accepted_customers"] == 0
    customer.post("/api/customers/cust_01/next-step", json={"path": "buy_out", "kind": "primary"})
    assert dash.get(f"{URL}/live").json()["accepted_customers"] == 1


# --- freshness and failure (FR-009, FR-014) -----------------------------------------------------------


def test_the_response_can_be_revalidated_cheaply_and_is_never_reused_blindly():
    store = InMemoryStore(PROFILES)
    dash = staff(store)
    first = dash.get(f"{URL}/live")
    tag = first.headers["etag"]
    assert first.headers["cache-control"] == "no-cache"
    again = dash.get(f"{URL}/live", headers={"If-None-Match": tag})
    assert again.status_code == 304 and again.content == b""
    assert again.headers["etag"] == tag


def test_the_tag_changes_when_an_acceptance_arrives_but_not_with_the_time():
    store = InMemoryStore(PROFILES)
    dash = staff(store)
    tag = dash.get(f"{URL}/live").headers["etag"]
    assert dash.get(f"{URL}/live").headers["etag"] == tag  # a later updated_at, the same tag
    store.record_acceptance(acc("cust_01"))
    r = dash.get(f"{URL}/live", headers={"If-None-Match": tag})
    assert r.status_code == 200 and r.headers["etag"] != tag and r.json()["accepted_customers"] == 1


def test_a_store_that_cannot_be_read_gives_the_plain_503_and_nothing_partial():
    class Broken(InMemoryStore):
        def latest_acceptances(self):
            raise RuntimeError("the table is missing")

    r = staff(Broken(PROFILES)).get(f"{URL}/live")
    assert r.status_code == 503 and r.json() == {"detail": "We can't load the live figures right now."}
    assert "table" not in r.text


def test_the_route_is_in_the_staff_router_and_needs_a_session():
    from crossroads.internal_api.routes import router

    assert f"{URL}/live" in {r.path for r in router.routes}


@pytest.mark.parametrize("path", ["/api/live", "/api/internal/live"])
def test_the_customer_api_does_not_serve_the_figures(path):
    c = TestClient(customer_app(store=InMemoryStore(PROFILES), cfg=Config()))
    assert c.get(path).status_code in (404, 405)
