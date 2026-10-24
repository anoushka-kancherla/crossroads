"""Schema and seed loader against a real TimescaleDB.

Skipped unless CROSSROADS_TEST_DB_URL points at one, for example:
  docker run -d -e POSTGRES_PASSWORD=crossroads -e POSTGRES_USER=crossroads \
    -e POSTGRES_DB=crossroads -p 55432:5432 timescale/timescaledb:latest-pg16
  CROSSROADS_TEST_DB_URL=postgresql://crossroads:crossroads@localhost:55432/crossroads pytest tests/db
The test creates and drops its own database, `crossroads_test`.
"""

import os
from decimal import Decimal as D

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.conninfo import make_conninfo  # noqa: E402

from crossroads.adapters.nessie import FakeNessie  # noqa: E402
from crossroads.db.repo import apply_schema, connect, refresh_aggregates  # noqa: E402
from crossroads.seed.load import seed  # noqa: E402
from crossroads.seed.profiles import generate_profiles  # noqa: E402

URL = os.environ.get("CROSSROADS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CROSSROADS_TEST_DB_URL is not set")

PROFILES = generate_profiles()


@pytest.fixture(scope="module")
def conn():
    admin = connect(URL, autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS crossroads_test WITH (FORCE)")
    admin.execute("CREATE DATABASE crossroads_test")
    c = connect(make_conninfo(URL, dbname="crossroads_test"), autocommit=True)
    yield c
    c.close()
    admin.execute("DROP DATABASE IF EXISTS crossroads_test WITH (FORCE)")
    admin.close()


@pytest.fixture(scope="module")
def seeded(conn):
    apply_schema(conn)
    nessie = FakeNessie()
    seed(conn, nessie, PROFILES)
    refresh_aggregates(conn)
    return nessie


def count(conn, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_the_schema_creates_hypertables_and_continuous_aggregates(conn, seeded):
    hypertables = {r[0] for r in conn.execute("SELECT hypertable_name FROM timescaledb_information.hypertables")}
    assert {"odometer_readings", "payments", "transactions"} <= hypertables
    caggs = {r[0] for r in conn.execute("SELECT view_name FROM timescaledb_information.continuous_aggregates")}
    assert {"monthly_miles", "monthly_payments", "monthly_spend"} <= caggs


def test_applying_the_schema_again_changes_nothing(conn, seeded):
    apply_schema(conn)
    assert count(conn, "customers") == 12


def test_every_profile_is_loaded(conn, seeded):
    assert count(conn, "customers") == count(conn, "vehicles") == count(conn, "contracts") == 12
    assert count(conn, "accounts") == 24
    assert count(conn, "bills") == sum(len(p.bills) for p in PROFILES)
    assert count(conn, "income") == sum(len(p.deposits) for p in PROFILES)
    assert count(conn, "transactions") == sum(len(p.transactions) for p in PROFILES)
    assert count(conn, "odometer_readings") == sum(len(p.readings) for p in PROFILES)


def test_the_tables_mirror_what_nessie_returns(conn, seeded):
    for p in PROFILES:
        got = dict(conn.execute("SELECT kind, balance FROM accounts WHERE customer_id = %s", (p.id,)))
        assert got == {"checking": p.checking, "savings": p.savings}
        bills = conn.execute("SELECT sum(monthly_amount) FROM bills WHERE customer_id = %s", (p.id,)).fetchone()[0]
        assert bills == sum((a for _, a in p.bills), D(0))
        cid = conn.execute("SELECT nessie_customer_id FROM customers WHERE id = %s", (p.id,)).fetchone()[0]
        assert cid and cid.startswith("fake-cust-")


def test_reseeding_creates_nothing_new_in_nessie_or_the_database(conn, seeded):
    before = {t: count(conn, t) for t in ("customers", "accounts", "bills", "income", "transactions")}
    ids = conn.execute("SELECT id, nessie_customer_id FROM customers ORDER BY id").fetchall()
    second = FakeNessie()
    seed(conn, second, PROFILES)
    assert second._n == 0, "nothing should be created in Nessie on a re-run"
    assert {t: count(conn, t) for t in before} == before
    assert conn.execute("SELECT id, nessie_customer_id FROM customers ORDER BY id").fetchall() == ids


def test_the_miles_aggregate_matches_the_last_reading(conn, seeded):
    for p in PROFILES:
        got = conn.execute("SELECT max(odometer) FROM monthly_miles WHERE customer_id = %s", (p.id,)).fetchone()[0]
        assert got == p.readings[-1][1]


def test_the_spend_aggregate_sums_the_transactions(conn, seeded):
    total = conn.execute("SELECT sum(amount) FROM transactions").fetchone()[0]
    assert conn.execute("SELECT sum(amount) FROM monthly_spend").fetchone()[0] == total
