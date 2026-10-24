"""The database store answers exactly like the in-memory store, so the API behaves the same on real data.

Skipped unless CROSSROADS_TEST_DB_URL points at a TimescaleDB (see test_seed_integration.py).
"""

import os

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.conninfo import make_conninfo  # noqa: E402

from crossroads.adapters.nessie import FakeNessie  # noqa: E402
from crossroads.config import Config  # noqa: E402
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
