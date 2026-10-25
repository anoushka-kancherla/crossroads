"""The acceptance log in a real TimescaleDB: a hypertable, read back with last() (skipped without
CROSSROADS_TEST_DB_URL). Everything here runs in a scratch database that the test creates and removes
itself, never in the application's own database."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.conninfo import make_conninfo  # noqa: E402

from crossroads.customer_api.store import Acceptance, DbStore  # noqa: E402
from crossroads.db.repo import apply_schema, connect, make_pool  # noqa: E402
from crossroads.seed.memory import InMemoryStore  # noqa: E402
from crossroads.seed.profiles import generate_profiles  # noqa: E402

URL = os.environ.get("CROSSROADS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CROSSROADS_TEST_DB_URL is not set")
T0 = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
SCRATCH = "crossroads_test_accept"


def acc(cid, path="buy_out", n=0, retained=True, revenue="100.00"):
    return Acceptance(cid, path, retained, D(revenue), T0 + timedelta(seconds=n))


@pytest.fixture(scope="module")
def dburl():
    admin = connect(URL, autocommit=True)
    admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
    admin.execute(f"CREATE DATABASE {SCRATCH}")
    url = make_conninfo(URL, dbname=SCRATCH)
    conn = connect(url, autocommit=True)
    apply_schema(conn)
    conn.close()
    yield url
    admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
    admin.close()


@pytest.fixture
def pool(dburl):
    p = make_pool(dburl)
    p.open()
    with p.connection() as c:
        c.execute("DELETE FROM acceptances")  # a clean log for each test, in the scratch database only
    yield p
    p.close()


def test_the_table_is_a_hypertable_and_the_schema_can_be_applied_twice(dburl):
    conn = connect(dburl, autocommit=True)
    apply_schema(conn)
    names = [r[0] for r in conn.execute("SELECT hypertable_name FROM timescaledb_information.hypertables")]
    assert "acceptances" in names
    cols = [
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'acceptances' ORDER BY ordinal_position"
        )
    ]
    assert cols == ["ts", "customer_id", "path", "retained", "revenue"]
    conn.close()


def test_an_entry_for_an_unknown_customer_is_accepted_there_is_no_foreign_key(pool):
    DbStore(pool).record_acceptance(acc("nobody"))
    assert DbStore(pool).acceptance_count() == 1


def test_last_returns_the_later_of_two_entries_for_one_customer(pool):
    s = DbStore(pool)
    s.record_acceptance(acc("cust_01", "buy_out", 1))
    s.record_acceptance(acc("cust_01", "keep_as_is", 5, retained=False, revenue="0.00"))
    s.record_acceptance(acc("cust_02", "buy_out", 2))
    latest = s.latest_acceptances()
    assert [(e.customer_id, e.path, e.retained) for e in latest] == [
        ("cust_01", "keep_as_is", False),
        ("cust_02", "buy_out", True),
    ]
    assert s.acceptance_count() == 3


def test_entries_survive_a_new_connection_pool_and_match_the_in_memory_store(dburl, pool):
    seq = [acc("cust_01", "buy_out", 1), acc("cust_02", "keep_as_is", 2, False, "0.00"), acc("cust_01", "refinance", 3)]
    mem = InMemoryStore(generate_profiles())
    for e in seq:
        DbStore(pool).record_acceptance(e)
        mem.record_acceptance(e)
    again = make_pool(dburl)  # a second pool stands in for a restart
    again.open()
    try:
        assert DbStore(again).latest_acceptances() == mem.latest_acceptances()
        assert DbStore(again).acceptance_count() == mem.acceptance_count() == 3
    finally:
        again.close()
