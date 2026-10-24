"""The snapshot table and the refresh job against a real TimescaleDB (skipped without CROSSROADS_TEST_DB_URL)."""

import os
from datetime import UTC, datetime
from decimal import Decimal as D

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.conninfo import make_conninfo  # noqa: E402

from crossroads.adapters.nessie import FakeNessie  # noqa: E402
from crossroads.config import Config  # noqa: E402
from crossroads.customer_api.store import DbStore  # noqa: E402
from crossroads.db.repo import apply_schema, connect, make_pool  # noqa: E402
from crossroads.engine.portfolio import CustomerResult  # noqa: E402
from crossroads.explain.service import ExplainService  # noqa: E402
from crossroads.internal_api.portfolio_service import build_portfolio, refresh_snapshots  # noqa: E402
from crossroads.internal_api.snapshots import DbSnapshots, InMemorySnapshots, SnapshotRow  # noqa: E402
from crossroads.seed.load import seed  # noqa: E402
from crossroads.seed.memory import InMemoryStore  # noqa: E402
from crossroads.seed.profiles import generate_profiles  # noqa: E402

URL = os.environ.get("CROSSROADS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CROSSROADS_TEST_DB_URL is not set")
PROFILES = generate_profiles()
CFG = Config()
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def pool():
    admin = connect(URL, autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS crossroads_test_snap WITH (FORCE)")
    admin.execute("CREATE DATABASE crossroads_test_snap")
    url = make_conninfo(URL, dbname="crossroads_test_snap")
    conn = connect(url, autocommit=True)
    apply_schema(conn)
    seed(conn, FakeNessie(), PROFILES)
    conn.close()
    p = make_pool(url)
    p.open()
    yield p
    p.close()
    admin.execute("DROP DATABASE IF EXISTS crossroads_test_snap WITH (FORCE)")
    admin.close()


def test_a_snapshot_round_trips_including_a_customer_with_no_recommendation(pool):
    snaps = DbSnapshots(pool)
    rows = [
        SnapshotRow(CustomerResult("cust_01", "buy_out", D("25729"), D("31118"), True, D("7212.23"), True), NOW),
        SnapshotRow(CustomerResult("cust_04", None, None, D("30815"), False, D("0"), True), NOW),
    ]
    snaps.save(rows)
    snaps.save(rows)  # saving again updates, no duplicates
    assert snaps.load() == rows


def test_refreshing_against_the_database_matches_refreshing_against_memory(pool):
    db_snaps, mem_snaps = DbSnapshots(pool), InMemorySnapshots()
    refresh_snapshots(DbStore(pool), db_snaps, CFG, ExplainService(None), now=NOW)
    refresh_snapshots(InMemoryStore(PROFILES), mem_snaps, CFG, ExplainService(None), now=NOW)
    assert db_snaps.load() == mem_snaps.load()
    assert build_portfolio(db_snaps.load()) == build_portfolio(mem_snaps.load())
    assert build_portfolio(db_snaps.load()).customers_total == 12
