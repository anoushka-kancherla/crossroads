"""POST /api/customers/{id}/sync: re-read one customer's bank figures from Nessie (FR-039)."""

from fastapi.testclient import TestClient

from crossroads.adapters.nessie import FakeNessie, NessieError
from crossroads.customer_api.main import create_app
from crossroads.net import SlidingWindowLimiter
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

PROFILES = generate_profiles()


class RealStub(FakeNessie):
    """A client the app treats as the live Nessie API."""

    real = True


class Broken(RealStub):
    def get_accounts(self, customer_id):
        raise NessieError("Nessie answered 500 for GET /customers/x/accounts")


def make(nessie=None, limiter=None, peer="93.184.216.34"):
    app = create_app(store=InMemoryStore(PROFILES), nessie=nessie, limiter=limiter)
    return TestClient(app, client=(peer, 50000)), app


def sync(client, cid="cust_01"):
    return client.post(f"/api/customers/{cid}/sync")


def test_a_real_bank_connection_refreshes_the_money_panel_and_says_when():
    client, _ = make(RealStub())
    r = sync(client)
    assert r.status_code == 200
    money = r.json()["money"]
    assert money["source"] == "nessie" and money["source_label"].endswith("Capital One Nessie (sandbox)")
    assert money["synced_at"] is not None
    assert (money["checking"], money["savings"]) == ("3100.00", "1800.00")  # the same engine inputs as before


def test_the_overview_shows_the_new_source_and_sync_time_afterwards():
    client, _ = make(RealStub())
    before = client.get("/api/customers/cust_01/overview").json()["money"]
    assert before["source"] == "demo" and before["synced_at"] is None
    sync(client)
    after = client.get("/api/customers/cust_01/overview").json()["money"]
    assert after["source"] == "nessie" and after["synced_at"] is not None


def test_with_no_bank_configured_it_says_so_and_changes_nothing():
    client, _ = make(None)
    r = sync(client)
    assert r.status_code == 503 and r.json() == {"detail": "We couldn't refresh your bank figures right now."}
    assert client.get("/api/customers/cust_01/overview").json()["money"]["synced_at"] is None


def test_a_demo_customer_is_not_connected_to_a_bank():
    client, _ = make(FakeNessie())
    r = sync(client)
    assert r.status_code == 409 and r.json() == {"detail": "This customer is demo data, so there's no bank to sync."}


def test_when_nessie_fails_the_message_is_plain_and_the_figures_stay():
    client, _ = make(Broken())
    r = sync(client)
    assert r.status_code == 503 and r.json() == {"detail": "We couldn't refresh your bank figures right now."}
    assert "Nessie answered" not in r.text and "/customers/" not in r.text
    assert client.get("/api/customers/cust_01/overview").json()["money"]["source"] == "demo"


def test_an_unknown_customer_is_a_404_not_a_call_to_nessie():
    client, _ = make(RealStub())
    assert sync(client, "nobody").status_code == 404


def test_it_is_limited_per_client_address_and_says_how_long_to_wait():
    now = [0.0]
    limiter = SlidingWindowLimiter(20, 3600, clock=lambda: now[0])
    client, app = make(RealStub(), limiter)
    assert [sync(client).status_code for _ in range(20)] == [200] * 20
    r = sync(client)
    assert r.status_code == 429 and r.headers["retry-after"] == "3600"
    assert r.json() == {"detail": "You've made a lot of requests. Please try again later."}
    other = TestClient(app, client=("151.101.2.9", 1))
    assert sync(other).status_code == 200, "a different address is not affected"
    now[0] += 3601
    assert sync(client).status_code == 200


def test_the_limit_counts_even_when_the_bank_is_unavailable():
    limiter = SlidingWindowLimiter(2, 3600, clock=lambda: 0.0)
    client, _ = make(None, limiter)
    assert [sync(client).status_code for _ in range(3)] == [503, 503, 429]


def test_the_route_returns_only_the_selected_customers_money():
    client, _ = make(RealStub())
    a = sync(client, "cust_01").json()["money"]
    b = sync(client, "cust_02").json()["money"]
    assert a != b and set(a) == set(b)
    assert "customer" not in sync(client).json()
