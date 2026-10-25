"""Real SerpApi listing quotes are cached with their source, never overwritten by demo data, and the
market value says where it came from. Skipped unless CROSSROADS_TEST_DB_URL is set."""

import os
from decimal import Decimal as D

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.conninfo import make_conninfo  # noqa: E402

from crossroads.adapters.listings import FakeListings, ListingQuote  # noqa: E402
from crossroads.adapters.nessie import FakeNessie  # noqa: E402
from crossroads.config import Config  # noqa: E402
from crossroads.customer_api.overview import build_overview  # noqa: E402
from crossroads.customer_api.store import DbStore  # noqa: E402
from crossroads.db.repo import apply_schema, connect, make_pool  # noqa: E402
from crossroads.seed.load import seed, warm_listing_cache  # noqa: E402
from crossroads.seed.profiles import generate_profiles  # noqa: E402

URL = os.environ.get("CROSSROADS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CROSSROADS_TEST_DB_URL is not set")
PROFILES = generate_profiles()
FIRST = PROFILES[0]
REAL = ListingQuote(low=D(30001), median=D(31111), high=D(32222), n=9)
KEY = (FIRST.vehicle.make, FIRST.vehicle.model, FIRST.vehicle.year, FIRST.zip)


@pytest.fixture(scope="module")
def db_url():
    admin = connect(URL, autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS crossroads_test_listings WITH (FORCE)")
    admin.execute("CREATE DATABASE crossroads_test_listings")
    url = make_conninfo(URL, dbname="crossroads_test_listings")
    conn = connect(url, autocommit=True)
    apply_schema(conn)
    seed(conn, FakeNessie(), PROFILES)
    conn.close()
    yield url
    admin.execute("DROP DATABASE IF EXISTS crossroads_test_listings WITH (FORCE)")
    admin.close()


def source_of(conn, key):
    return conn.execute(
        "SELECT source, median FROM listing_cache WHERE make=%s AND model=%s AND year=%s AND zip=%s", key
    ).fetchone()


def test_before_any_warm_up_every_quote_is_demo_data(db_url):
    conn = connect(db_url, autocommit=True)
    assert {r[0] for r in conn.execute("SELECT source FROM listing_cache")} == {"demo"}
    conn.close()


def test_warming_stores_the_real_quote_as_serpapi_and_leaves_the_others_as_demo(db_url):
    conn = connect(db_url, autocommit=True)
    warmed, fell_back = warm_listing_cache(conn, FakeListings({KEY: REAL}), PROFILES)
    assert warmed == 1 and fell_back >= 1
    assert source_of(conn, KEY) == ("serpapi", D("31111.00"))
    assert "demo" in {r[0] for r in conn.execute("SELECT source FROM listing_cache")}
    conn.close()


def test_seeding_again_never_overwrites_a_real_quote_with_demo_data(db_url):
    conn = connect(db_url, autocommit=True)
    seed(conn, FakeNessie(), PROFILES)
    assert source_of(conn, KEY) == ("serpapi", D("31111.00"))
    conn.close()


def test_a_lookup_that_fails_leaves_the_existing_quote_alone(db_url):
    class Broken:
        def lookup(self, *a):
            raise RuntimeError("The listings search could not be reached.")

    conn = connect(db_url, autocommit=True)
    warmed, fell_back = warm_listing_cache(conn, Broken(), PROFILES)
    assert warmed == 0 and fell_back >= 1
    assert source_of(conn, KEY) == ("serpapi", D("31111.00"))
    conn.close()


def test_the_market_value_says_where_it_came_from(db_url):
    pool = make_pool(db_url)
    pool.open()
    try:
        store = DbStore(pool)
        real = build_overview(store.get_record(FIRST.id), store.monthly_miles(FIRST.id), Config()).market_value
        assert real.source == "serpapi" and real.source_label == "Google results via SerpApi"
        assert real.median == D("31111.00") and real.n_listings == 9
        other = next(p for p in PROFILES if (p.vehicle.make, p.vehicle.model, p.vehicle.year, p.zip) != KEY
                     and p.listing_median is not None)
        demo = build_overview(store.get_record(other.id), store.monthly_miles(other.id), Config()).market_value
        assert demo.source == "demo" and demo.source_label == "Demo data"
    finally:
        pool.close()


def test_a_customer_seeded_with_no_listings_stays_that_way_so_the_depreciation_fallback_is_still_shown(db_url):
    """FR-005: one demo customer has no market listings on purpose. A real quote must not erase that case."""
    none_profile = next(p for p in PROFILES if p.listing_median is None)
    key = (none_profile.vehicle.make, none_profile.vehicle.model, none_profile.vehicle.year, none_profile.zip)
    conn = connect(db_url, autocommit=True)
    warm_listing_cache(conn, FakeListings({key: REAL}), PROFILES)
    assert source_of(conn, key) is None, "no row, so the value comes from the depreciation estimate"
    conn.close()
