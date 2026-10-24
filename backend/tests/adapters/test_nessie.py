"""Nessie adapter: parsers, the in-memory fake, and the HTTP client against a mock transport."""

import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import httpx
import pytest

from crossroads.adapters.nessie import (
    FakeNessie,
    HttpNessie,
    NessieAccount,
    NessieBill,
    NessieDeposit,
    NessiePurchase,
    parse_account,
    parse_bill,
    parse_deposit,
    parse_purchase,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def fixture(name: str) -> dict:
    # Provisional fixtures: replace with captured responses when a Nessie key is available.
    return json.loads((FIXTURES / f"nessie_{name}.provisional.json").read_text())


def test_parsers_read_the_fixtures():
    assert parse_account(fixture("account")) == NessieAccount("5f00000000000000000000a1", "checking", D(3100))
    assert parse_bill(fixture("bill")) == NessieBill("5f00000000000000000000b1", "Rent or mortgage", D(1650))
    assert parse_deposit(fixture("deposit")) == NessieDeposit("5f00000000000000000000d1", date(2026, 10, 24), D(5200))
    assert parse_purchase(fixture("purchase")) == NessiePurchase(
        "5f00000000000000000000c1", date(2026, 10, 21), D("120.5"), "groceries"
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
    assert [a.id for a in accounts] == ["5f00000000000000000000a1"]


def test_the_http_client_surfaces_api_errors():
    client = HttpNessie("KEY", http=_mock(lambda r: httpx.Response(401, json={"message": "no"})))
    with pytest.raises(httpx.HTTPStatusError):
        client.get_bills("acct")


def test_the_http_client_needs_a_key():
    with pytest.raises(ValueError):
        HttpNessie("")
