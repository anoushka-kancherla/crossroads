"""The database store answers exactly like the in-memory store, so the API behaves the same on real data.

Skipped unless CROSSROADS_TEST_DB_URL points at a TimescaleDB (see test_seed_integration.py).
"""

import json
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.conninfo import make_conninfo  # noqa: E402

from crossroads.adapters.dealers import DealerLookupError, FakeDealers, parse_maps_results  # noqa: E402
from crossroads.adapters.nessie import FakeNessie  # noqa: E402
from crossroads.config import Config  # noqa: E402
from crossroads.customer_api.dealers_service import nearby_dealers  # noqa: E402
from crossroads.customer_api.overview import build_overview, build_spending  # noqa: E402
from crossroads.customer_api.store import DbStore  # noqa: E402
from crossroads.db.repo import apply_schema, connect, make_pool, refresh_aggregates  # noqa: E402
from crossroads.seed.load import seed  # noqa: E402
from crossroads.seed.memory import InMemoryStore  # noqa: E402
from crossroads.seed.profiles import generate_profiles  # noqa: E402

URL = os.environ.get("CROSSROADS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CROSSROADS_TEST_DB_URL is not set")

PROFILES = generate_profiles()
CFG = Config()


@pytest.fixture(scope="module")
def db_url():
    admin = connect(URL, autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS crossroads_test_store WITH (FORCE)")
    admin.execute("CREATE DATABASE crossroads_test_store")
    url = make_conninfo(URL, dbname="crossroads_test_store")
    conn = connect(url, autocommit=True)
    apply_schema(conn)
    seed(conn, FakeNessie(), PROFILES)
    refresh_aggregates(conn)
    conn.close()
    yield url
    admin.execute("DROP DATABASE IF EXISTS crossroads_test_store WITH (FORCE)")
    admin.close()


@pytest.fixture(scope="module")
def stores(db_url):
    pool = make_pool(db_url)
    pool.open()
    yield DbStore(pool), InMemoryStore(PROFILES)
    pool.close()


def test_the_picker_lists_match(stores):
    db, mem = stores
    assert db.list_customers() == mem.list_customers()


def test_every_record_matches(stores):
    db, mem = stores
    for p in PROFILES:
        a, b = db.get_record(p.id), mem.get_record(p.id)
        assert a.quote_updated_at is not None or b.quote is None
        # the cache timestamp is the only thing that legitimately differs
        assert (a.id, a.display_name, a.first_name, a.zip, a.vehicle, a.contract, a.end_date) == (
            b.id, b.display_name, b.first_name, b.zip, b.vehicle, b.contract, b.end_date)
        assert (a.readings, a.checking, a.savings, a.income, a.bills_total, a.quote) == (
            b.readings, b.checking, b.savings, b.income, b.bills_total, b.quote)


def test_the_monthly_aggregates_match(stores):
    db, mem = stores
    for p in PROFILES:
        assert db.monthly_miles(p.id) == mem.monthly_miles(p.id), p.id
        assert db.monthly_spend(p.id) == mem.monthly_spend(p.id), p.id


def test_the_overview_and_spending_responses_match(stores):
    db, mem = stores
    for p in PROFILES:
        a = build_overview(db.get_record(p.id), db.monthly_miles(p.id), CFG).model_dump()
        b = build_overview(mem.get_record(p.id), mem.monthly_miles(p.id), CFG).model_dump()
        a["market_value"].pop("updated_at")
        b["market_value"].pop("updated_at")
        assert a == b, p.id
        assert build_spending(db.monthly_spend(p.id)) == build_spending(mem.monthly_spend(p.id))


def test_an_unknown_customer_is_none(stores):
    assert stores[0].get_record("nobody") is None


CAPTURED = json.loads((Path(__file__).parent.parent / "fixtures" / "serpapi_maps_toyota.json").read_text())


def test_the_dealer_cache_round_trips_and_does_not_duplicate(stores):
    db, _ = stores
    dealers = parse_maps_results(CAPTURED)
    assert db.dealer_candidates("99999") is None  # never looked up
    db.save_dealer_candidates("99999", dealers)
    db.save_dealer_candidates("99999", dealers)  # saving again updates rather than duplicating
    got = db.dealer_candidates("99999")
    assert len(got) == len(dealers) == 12
    assert set(got) == set(dealers)


def test_dealers_are_ranked_from_the_cache_by_the_customers_own_coordinates(stores):
    db, _ = stores
    rec = db.get_record("cust_01")
    db.save_dealer_candidates(rec.zip, parse_maps_results(CAPTURED))
    top = nearby_dealers(db, None, rec)  # no client: it must come from the cache
    assert [d.name for d in top][0] == "Toyota of Plano" and len(top) == 3


def test_the_seed_pre_warms_each_zip_once_and_a_failed_zip_does_not_stop_the_rest(db_url):
    zips = {p.zip for p in PROFILES}
    conn = connect(db_url, autocommit=True)
    conn.execute("DELETE FROM dealer_cache")
    fake = FakeDealers(parse_maps_results(CAPTURED))
    assert seed(conn, FakeNessie(), PROFILES, fake) == []
    assert fake.calls == len(zips)
    assert seed(conn, FakeNessie(), PROFILES, fake) == []
    assert fake.calls == len(zips), "a cached ZIP must not be searched again"

    conn.execute("DELETE FROM dealer_cache")

    class OneZipDown:
        def search(self, zip_code, lat, lng):
            if zip_code == "75024":
                raise DealerLookupError("down")
            return parse_maps_results(CAPTURED)

    assert seed(conn, FakeNessie(), PROFILES, OneZipDown()) == ["75024"]
    cached = {r[0] for r in conn.execute("SELECT DISTINCT zip FROM dealer_cache")}
    assert cached == zips - {"75024"}
    conn.close()


def test_the_money_source_is_demo_for_the_fake_and_nessie_only_when_every_account_says_so(db_url, stores):
    db, _ = stores
    assert db.get_record("cust_01").data_source == "demo"  # seeded from the in-memory fake
    conn = connect(db_url, autocommit=True)
    try:
        conn.execute("UPDATE accounts SET source = 'nessie' WHERE customer_id = 'cust_01' AND kind = 'checking'")
        assert db.get_record("cust_01").data_source == "demo", "one account from Nessie is not enough to claim it"
        conn.execute("UPDATE accounts SET source = 'nessie' WHERE customer_id = 'cust_01'")
        assert db.get_record("cust_01").data_source == "nessie"
        overview = build_overview(db.get_record("cust_01"), db.monthly_miles("cust_01"), CFG)
        assert overview.money.source_label.endswith("Capital One Nessie (sandbox)")
    finally:
        conn.execute("UPDATE accounts SET source = 'demo' WHERE customer_id = 'cust_01'")
        conn.close()
