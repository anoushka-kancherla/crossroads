"""Nessie adapter: parsers, the in-memory fake, and the HTTP client against a mock transport."""

import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import httpx
import pytest

from crossroads.adapters.nessie import (
    BASE_URL,
    FakeNessie,
    HttpNessie,
    NessieAccount,
    NessieBill,
    NessieDeposit,
    NessieError,
    NessiePurchase,
    parse_account,
    parse_bill,
    parse_deposit,
    parse_purchase,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def fixture(name: str) -> dict:
    # Captured from the live Nessie API (one synthetic demo customer), not written from the documentation.
    return json.loads((FIXTURES / f"nessie_{name}.json").read_text())


def test_parsers_read_the_fixtures():
    assert parse_account(fixture("account")) == NessieAccount(fixture("account")["_id"], "checking", D(3100))
    assert parse_bill(fixture("bill")) == NessieBill(fixture("bill")["_id"], "Internet", D(106))
    assert parse_deposit(fixture("deposit")) == NessieDeposit(fixture("deposit")["_id"], date(2026, 8, 25), D(5200))
    assert parse_purchase(fixture("purchase")) == NessiePurchase(
        fixture("purchase")["_id"], date(2026, 7, 26), D(477), "groceries"
    )


def test_the_fake_returns_the_same_shapes_as_the_real_parsers():
    fake = FakeNessie()
    cid = fake.create_customer("Maya", "Ortiz", "75024")
    aid = fake.create_account(cid, "checking", D(3100))
    fake.create_bill(aid, "Rent or mortgage", D(1650))
    fake.create_deposit(aid, date(2026, 10, 24), D(5200), "Payroll")
    fake.create_purchase(aid, date(2026, 10, 21), D("120.5"), "groceries")
    assert type(fake.get_accounts(cid)[0]) is type(parse_account(fixture("account")))
    assert type(fake.get_bills(aid)[0]) is type(parse_bill(fixture("bill")))
    assert type(fake.get_deposits(aid)[0]) is type(parse_deposit(fixture("deposit")))
    assert type(fake.get_purchases(aid)[0]) is type(parse_purchase(fixture("purchase")))


def test_the_fake_reads_back_what_was_created():
    fake = FakeNessie()
    cid = fake.create_customer("Maya", "Ortiz", "75024")
    aid = fake.create_account(cid, "savings", D(1800))
    assert [(a.id, a.kind, a.balance) for a in fake.get_accounts(cid)] == [(aid, "savings", D(1800))]
    assert fake.get_bills(aid) == []
    assert fake.get_accounts("someone-else") == []


def test_the_fake_issues_unique_ids():
    fake = FakeNessie()
    cid = fake.create_customer("A", "B", "75024")
    ids = {cid, fake.create_account(cid, "checking", D(1)), fake.create_account(cid, "savings", D(1))}
    assert len(ids) == 3


def _mock(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_the_http_client_sends_the_key_and_returns_the_created_id():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.url.params.get("key")))
        return httpx.Response(201, json={"code": 201, "objectCreated": {"_id": "abc123"}})

    client = HttpNessie("KEY", http=_mock(handler))
    assert client.create_customer("Maya", "Ortiz", "75024") == "abc123"
    assert client.create_account("abc123", "checking", D(3100)) == "abc123"
    assert seen == [("POST", "/customers", "KEY"), ("POST", "/customers/abc123/accounts", "KEY")]


def test_the_http_client_reads_accounts_and_ignores_other_account_types():
    rows = [fixture("account"), {**fixture("account"), "_id": "cc1", "type": "Credit Card"}]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=rows)

    accounts = HttpNessie("KEY", http=_mock(handler)).get_accounts("cust")
    assert [a.id for a in accounts] == [fixture("account")["_id"]]


def test_the_http_client_surfaces_api_errors_without_the_key():
    secret = "SECRET-KEY-VALUE"
    client = HttpNessie(secret, http=_mock(lambda r: httpx.Response(401, json={"message": "no"})))
    with pytest.raises(NessieError) as caught:
        client.get_bills("acct")
    assert "401" in str(caught.value) and "/accounts/acct/bills" in str(caught.value)
    # An httpx error message carries the full URL, key included, so nothing may be chained to it.
    assert secret not in str(caught.value) and caught.value.__cause__ is None and caught.value.__suppress_context__


def test_a_network_failure_is_also_reported_without_the_key():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom for https://x/?key=SECRET-KEY-VALUE")

    with pytest.raises(NessieError) as caught:
        HttpNessie("SECRET-KEY-VALUE", http=_mock(down)).get_bills("acct")
    assert "SECRET-KEY-VALUE" not in str(caught.value) and caught.value.__cause__ is None


def test_the_http_client_needs_a_key():
    with pytest.raises(ValueError):
        HttpNessie("")


def test_the_real_base_url_is_https():
    # Found against the live API: plain http://api.nessieisreal.com refuses the connection.
    assert BASE_URL == "https://api.nessieisreal.com"


def test_a_purchase_uses_an_existing_merchant():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=[{"_id": "m1", "name": "Shop"}])
        return httpx.Response(201, json={"objectCreated": {"_id": "p1"}})

    assert HttpNessie("KEY", http=_mock(handler)).create_purchase("acct", date(2026, 9, 1), D(40), "Groceries") == "p1"
    assert calls == [("GET", "/merchants"), ("POST", "/accounts/acct/purchases")]


def test_a_purchase_creates_a_merchant_when_the_account_has_none():
    """The live API returned an empty merchant list, so the first purchase used to crash on [0]."""
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[])
        bodies.append((request.url.path, json.loads(request.content)))
        return httpx.Response(201, json={"objectCreated": {"_id": "new1"}})

    client = HttpNessie("KEY", http=_mock(handler))
    assert client.create_purchase("acct", date(2026, 9, 1), D(40), "Groceries") == "new1"
    client.create_purchase("acct", date(2026, 9, 2), D(10), "Fuel")
    paths = [p for p, _ in bodies]
    assert paths == ["/merchants", "/accounts/acct/purchases", "/accounts/acct/purchases"], "created once, reused"
    assert bodies[1][1]["merchant_id"] == "new1"
    assert isinstance(bodies[0][1]["category"], str), "the live API refuses a list here"


def test_a_deposit_is_sent_with_the_status_the_live_api_requires():
    """Found against the live API: a deposit without `status` is refused with a 400."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(201, json={"objectCreated": {"_id": "d1"}})

    HttpNessie("KEY", http=_mock(handler)).create_deposit("acct", date(2026, 9, 1), D(5200), "Payroll")
    assert seen[0]["status"] == "completed" and seen[0]["amount"] == 5200.0


def test_a_purchase_is_sent_with_a_status_or_the_live_api_cannot_read_it_back():
    """Found against the live API: a purchase created without `status` is accepted, then every GET of
    the account's purchases fails validation."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[{"_id": "m1"}])
        seen.append(json.loads(request.content))
        return httpx.Response(201, json={"objectCreated": {"_id": "p1"}})

    HttpNessie("KEY", http=_mock(handler)).create_purchase("acct", date(2026, 9, 1), D(40), "Groceries")
    assert seen[0]["status"] == "completed"
