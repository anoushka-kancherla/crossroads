"""TimescaleDB compression on the three hypertables (Tiger Data): old chunks compress, and every query the
app makes returns the same answers afterwards. Skipped unless CROSSROADS_TEST_DB_URL is set."""

import os

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.conninfo import make_conninfo  # noqa: E402

from crossroads.adapters.nessie import FakeNessie  # noqa: E402
from crossroads.customer_api.overview import build_spending  # noqa: E402
from crossroads.customer_api.store import DbStore  # noqa: E402
from crossroads.db.repo import (  # noqa: E402
    HYPERTABLES,
    apply_schema,
    compress_old_chunks,
    compression_stats,
    connect,
    make_pool,
    refresh_aggregates,
)
from crossroads.seed.load import seed  # noqa: E402
from crossroads.seed.profiles import generate_profiles  # noqa: E402

URL = os.environ.get("CROSSROADS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CROSSROADS_TEST_DB_URL is not set")
PROFILES = generate_profiles()


@pytest.fixture(scope="module")
def db_url():
    admin = connect(URL, autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS crossroads_test_compress WITH (FORCE)")
    admin.execute("CREATE DATABASE crossroads_test_compress")
    url = make_conninfo(URL, dbname="crossroads_test_compress")
    conn = connect(url, autocommit=True)
    apply_schema(conn)
    seed(conn, FakeNessie(), PROFILES)
    refresh_aggregates(conn)
    conn.close()
    yield url
    admin.execute("DROP DATABASE IF EXISTS crossroads_test_compress WITH (FORCE)")
    admin.close()


def snapshot(url):
    pool = make_pool(url)
    pool.open()
    try:
        store = DbStore(pool)
        return {
            p.id: (
                store.monthly_miles(p.id),
                store.get_record(p.id).readings,
                build_spending(store.monthly_spend(p.id)),
            )
            for p in PROFILES
        }
    finally:
        pool.close()


def test_every_hypertable_has_a_compression_policy(db_url):
    conn = connect(db_url, autocommit=True)
    tables = {r[0] for r in conn.execute(
        "SELECT hypertable_name FROM timescaledb_information.jobs WHERE proc_name = 'policy_compression'"
    )}
    conn.close()
    assert tables == set(HYPERTABLES)


def test_old_chunks_compress_and_the_app_sees_the_same_data(db_url):
    before = snapshot(db_url)
    conn = connect(db_url, autocommit=True)
    compressed = compress_old_chunks(conn)
    stats = compression_stats(conn)
    conn.close()
    assert compressed > 0, "the seeded history is older than the policy's age, so some chunks must compress"
    assert {s.table for s in stats} == set(HYPERTABLES)
    for s in stats:
        assert s.chunks_compressed > 0 and s.bytes_before > 0 and s.bytes_after > 0, s
    assert snapshot(db_url) == before, "compression must not change any answer the app gives"


def test_seeding_again_after_compression_still_works(db_url):
    conn = connect(db_url, autocommit=True)
    try:
        seed(conn, FakeNessie(), PROFILES)  # idempotent: updates rows that now sit in compressed chunks
        refresh_aggregates(conn)
    finally:
        conn.close()
