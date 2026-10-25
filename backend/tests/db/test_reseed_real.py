"""T091: seeding with a real Nessie client replaces rows an earlier demo seed made from the in-memory fake,
without ever creating a second Nessie customer for someone who already has a real one.
Skipped unless CROSSROADS_TEST_DB_URL is set."""

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.conninfo import make_conninfo  # noqa: E402

from crossroads.adapters.nessie import FakeNessie  # noqa: E402
from crossroads.db.repo import apply_schema, connect  # noqa: E402
from crossroads.seed.load import seed  # noqa: E402
from crossroads.seed.profiles import generate_profiles  # noqa: E402

URL = os.environ.get("CROSSROADS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CROSSROADS_TEST_DB_URL is not set")
PROFILES = generate_profiles()[:3]


class StubReal(FakeNessie):
    """Behaves like the live API as far as the seed can tell: it is real, and its ids are UUIDs."""

    real = True

    def __init__(self):
        super().__init__()
        self.customers_created = 0

    def _id(self, prefix: str) -> str:
        return str(uuid.uuid4())

    def create_customer(self, *a):
        self.customers_created += 1
        return super().create_customer(*a)


@pytest.fixture()
def conn():
    admin = connect(URL, autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS crossroads_test_reseed WITH (FORCE)")
    admin.execute("CREATE DATABASE crossroads_test_reseed")
    c = connect(make_conninfo(URL, dbname="crossroads_test_reseed"), autocommit=True)
    apply_schema(c)
    yield c
    c.close()
    admin.execute("DROP DATABASE IF EXISTS crossroads_test_reseed WITH (FORCE)")
    admin.close()


def counts(conn):
    return {
        t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        for t in ("customers", "accounts", "bills", "income", "transactions")
    }


def test_a_demo_seed_is_replaced_by_a_real_one_with_no_duplicates(conn):
    seed(conn, FakeNessie(), PROFILES)
    before = counts(conn)
    assert all(r[0].startswith("fake-") for r in conn.execute("SELECT nessie_customer_id FROM customers"))
    assert {r[0] for r in conn.execute("SELECT source FROM accounts")} == {"demo"}

    real = StubReal()
    seed(conn, real, PROFILES)
    assert real.customers_created == len(PROFILES), "each demo customer is created once in the real service"
    assert counts(conn) == before, "same number of rows: the demo rows were replaced, not added to"
    assert not any(r[0].startswith("fake-") for r in conn.execute("SELECT nessie_customer_id FROM customers"))
    assert {r[0] for r in conn.execute("SELECT source FROM accounts")} == {"nessie"}


def test_seeding_with_the_real_client_again_creates_nothing_new(conn):
    real = StubReal()
    seed(conn, real, PROFILES)
    ids = sorted(r[0] for r in conn.execute("SELECT nessie_customer_id FROM customers"))
    seed(conn, real, PROFILES)
    assert real.customers_created == len(PROFILES), "a customer who already has a real account is never re-created"
    assert sorted(r[0] for r in conn.execute("SELECT nessie_customer_id FROM customers")) == ids


def test_seeding_with_the_fake_never_touches_real_rows(conn):
    real = StubReal()
    seed(conn, real, PROFILES)
    ids = sorted(r[0] for r in conn.execute("SELECT nessie_customer_id FROM customers"))
    seed(conn, FakeNessie(), PROFILES)
    assert sorted(r[0] for r in conn.execute("SELECT nessie_customer_id FROM customers")) == ids
    assert {r[0] for r in conn.execute("SELECT source FROM accounts")} == {"nessie"}


def test_a_customer_with_real_ids_but_an_interrupted_seed_is_not_duplicated(conn):
    """If a crash left real ids with the default source, they are still real: the id decides, not the flag."""
    real = StubReal()
    seed(conn, real, PROFILES)
    conn.execute("UPDATE accounts SET source = 'demo'")  # as if read_back never ran
    seed(conn, real, PROFILES)
    assert real.customers_created == len(PROFILES)


def test_syncing_one_customer_pulls_their_new_balance_and_leaves_the_others_alone(conn):
    from crossroads.customer_api.store import DbStore, NotConnected
    from crossroads.db.repo import make_pool

    real = StubReal()
    seed(conn, real, PROFILES)
    cid = PROFILES[0].id
    others_before = conn.execute(
        "SELECT customer_id, kind, balance FROM accounts WHERE customer_id <> %s ORDER BY 1, 2", (cid,)
    ).fetchall()
    nessie_cid = conn.execute("SELECT nessie_customer_id FROM customers WHERE id = %s", (cid,)).fetchone()[0]
    for acct in real._accounts[nessie_cid]:  # the bank moves money
        if acct["type"] == "Checking":
            acct["balance"] = "9999.00"

    pool = make_pool(make_conninfo(URL, dbname="crossroads_test_reseed"))
    pool.open()
    try:
        store = DbStore(pool)
        rec = store.sync_from_nessie(cid, real)
        assert rec.checking == 9999 and rec.data_source == "nessie" and rec.synced_at is not None
        assert conn.execute(
            "SELECT customer_id, kind, balance FROM accounts WHERE customer_id <> %s ORDER BY 1, 2", (cid,)
        ).fetchall() == others_before
        assert store.sync_from_nessie("nobody", real) is None
        with pytest.raises(NotConnected):  # the fake is not a bank
            store.sync_from_nessie(cid, FakeNessie())
    finally:
        pool.close()


def test_a_demo_customer_cannot_be_synced(conn):
    from crossroads.customer_api.store import DbStore, NotConnected
    from crossroads.db.repo import make_pool

    seed(conn, FakeNessie(), PROFILES)
    pool = make_pool(make_conninfo(URL, dbname="crossroads_test_reseed"))
    pool.open()
    try:
        with pytest.raises(NotConnected):
            DbStore(pool).sync_from_nessie(PROFILES[0].id, StubReal())
    finally:
        pool.close()
