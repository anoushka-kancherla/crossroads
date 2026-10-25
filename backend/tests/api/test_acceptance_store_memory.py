"""The in-memory acceptance log, which stands in for the database in tests (FR-001, FR-007)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from crossroads.customer_api.store import Acceptance
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def acc(cid, path="buy_out", n=0, retained=True, revenue="100.00"):
    return Acceptance(cid, path, retained, D(revenue), T0 + timedelta(seconds=n))


def store():
    return InMemoryStore(generate_profiles())


def test_an_empty_log_has_nothing():
    s = store()
    assert s.latest_acceptances() == [] and s.acceptance_count() == 0


def test_recording_appends_and_never_replaces():
    s = store()
    s.record_acceptance(acc("cust_01", n=1))
    s.record_acceptance(acc("cust_01", "keep_as_is", n=2))
    assert s.acceptance_count() == 2


def test_the_latest_acceptance_per_customer_is_returned_once_each():
    s = store()
    s.record_acceptance(acc("cust_01", "buy_out", 1))
    s.record_acceptance(acc("cust_02", "buy_out", 2))
    s.record_acceptance(acc("cust_01", "keep_as_is", 3, retained=False, revenue="0.00"))
    latest = s.latest_acceptances()
    assert [e.customer_id for e in latest] == ["cust_01", "cust_02"]
    assert latest[0].path == "keep_as_is" and latest[0].retained is False


def test_when_two_acceptances_share_an_instant_the_later_recorded_one_wins():
    s = store()
    s.record_acceptance(acc("cust_01", "buy_out", 5))
    s.record_acceptance(acc("cust_01", "keep_as_is", 5))
    assert [e.path for e in s.latest_acceptances()] == ["keep_as_is"]


def test_an_acceptance_that_arrives_late_does_not_replace_a_newer_one():
    s = store()
    s.record_acceptance(acc("cust_01", "keep_as_is", 9))
    s.record_acceptance(acc("cust_01", "buy_out", 3))
    assert [e.path for e in s.latest_acceptances()] == ["keep_as_is"]
