"""Capital One Nessie behind an interface (principle IV): a real HTTP client and an in-memory fake.

The response shapes parsed here are PROVISIONAL: written from Nessie's public documentation and
checked against `tests/fixtures/nessie_*.provisional.json`. Replace the fixtures with captured real
responses when a `NESSIE_API_KEY` is available (task T013) and adjust the parsers if they differ.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

import httpx

BASE_URL = "https://api.nessieisreal.com"  # plain http refuses the connection (found against the live API)
_KINDS = ("checking", "savings")


class NessieError(Exception):
    """A Nessie request failed. The message never carries a URL or key."""


@dataclass(frozen=True)
class NessieAccount:
    id: str
    kind: str  # "checking" | "savings"
    balance: Decimal


@dataclass(frozen=True)
class NessieBill:
    id: str
    payee: str
    amount: Decimal


@dataclass(frozen=True)
class NessieDeposit:
    id: str
    on: date
    amount: Decimal


@dataclass(frozen=True)
class NessiePurchase:
    id: str
    on: date
    amount: Decimal
    category: str


def _d(x: object) -> Decimal:
    return Decimal(str(x))


def parse_account(j: dict) -> NessieAccount:
    return NessieAccount(j["_id"], str(j["type"]).lower(), _d(j["balance"]))


def parse_bill(j: dict) -> NessieBill:
    return NessieBill(j["_id"], j["payee"], _d(j["payment_amount"]))


def parse_deposit(j: dict) -> NessieDeposit:
    return NessieDeposit(j["_id"], date.fromisoformat(j["transaction_date"]), _d(j["amount"]))


def parse_purchase(j: dict) -> NessiePurchase:
    return NessiePurchase(
        j["_id"], date.fromisoformat(j["purchase_date"]), _d(j["amount"]), j.get("description", "")
    )


class NessieClient(Protocol):
    def create_customer(self, first_name: str, last_name: str, zip_code: str) -> str: ...
    def create_account(self, customer_id: str, kind: str, balance: Decimal) -> str: ...
    def create_bill(self, account_id: str, payee: str, amount: Decimal) -> str: ...
    def create_deposit(self, account_id: str, on: date, amount: Decimal, description: str) -> str: ...
    def create_purchase(self, account_id: str, on: date, amount: Decimal, description: str) -> str: ...
    def get_accounts(self, customer_id: str) -> list[NessieAccount]: ...
    def get_bills(self, account_id: str) -> list[NessieBill]: ...
    def get_deposits(self, account_id: str) -> list[NessieDeposit]: ...
    def get_purchases(self, account_id: str) -> list[NessiePurchase]: ...


class HttpNessie:
    """The real Nessie API. Used only from the seed script, never at request time."""

    def __init__(self, api_key: str, base_url: str = BASE_URL, http: httpx.Client | None = None):
        if not api_key:
            raise ValueError("NESSIE_API_KEY is required")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=15)
        self._merchant: str | None = None

    def _send(self, method: str, path: str, **kwargs):
        """One request. Every failure becomes a NessieError with the status and path only: an httpx
        error message holds the full URL, API key included, so it is never chained or shown."""
        try:
            r = self._http.request(method, f"{self._base}{path}", params={"key": self._key}, **kwargs)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise NessieError(f"Nessie answered {e.response.status_code} for {method} {path}") from None
        except (httpx.HTTPError, ValueError):
            raise NessieError(f"Nessie could not be reached or answered badly for {method} {path}") from None

    def _get(self, path: str):
        return self._send("GET", path)

    def _post(self, path: str, body: dict) -> str:
        try:
            return self._send("POST", path, json=body)["objectCreated"]["_id"]
        except (KeyError, TypeError):
            raise NessieError(f"Nessie's answer to POST {path} had no created object") from None

    def _merchant_id(self) -> str:
        if self._merchant is None:
            existing = self._get("/merchants")
            if existing:
                self._merchant = existing[0]["_id"]
            else:  # a fresh sandbox can have none, so create one to attach purchases to
                self._merchant = self._post(
                    "/merchants",
                    {"name": "Crossroads demo merchant", "category": "demo",
                     "address": {"street_number": "100", "street_name": "Main St", "city": "Anytown",
                                 "state": "TX", "zip": "75024"},
                     "geocode": {"lat": 33.0, "lng": -96.8}},
                )
        return self._merchant

    def create_customer(self, first_name: str, last_name: str, zip_code: str) -> str:
        address = {"street_number": "100", "street_name": "Main St", "city": "Anytown",
                   "state": "TX", "zip": zip_code}
        return self._post("/customers", {"first_name": first_name, "last_name": last_name, "address": address})

    def create_account(self, customer_id: str, kind: str, balance: Decimal) -> str:
        body = {"type": kind.capitalize(), "nickname": kind.capitalize(), "rewards": 0, "balance": int(balance)}
        return self._post(f"/customers/{customer_id}/accounts", body)

    def create_bill(self, account_id: str, payee: str, amount: Decimal) -> str:
        body = {"status": "recurring", "payee": payee, "nickname": payee,
                "payment_date": date.today().isoformat(), "recurring_date": 1,
                "payment_amount": float(amount)}
        return self._post(f"/accounts/{account_id}/bills", body)

    def create_deposit(self, account_id: str, on: date, amount: Decimal, description: str) -> str:
        body = {"medium": "balance", "transaction_date": on.isoformat(), "status": "completed",
                "amount": float(amount), "description": description}
        return self._post(f"/accounts/{account_id}/deposits", body)

    def create_purchase(self, account_id: str, on: date, amount: Decimal, description: str) -> str:
        body = {"merchant_id": self._merchant_id(), "medium": "balance", "status": "completed",
                "purchase_date": on.isoformat(), "amount": float(amount), "description": description}
        return self._post(f"/accounts/{account_id}/purchases", body)

    def get_accounts(self, customer_id: str) -> list[NessieAccount]:
        rows = self._get(f"/customers/{customer_id}/accounts")
        return [parse_account(j) for j in rows if str(j.get("type", "")).lower() in _KINDS]

    def get_bills(self, account_id: str) -> list[NessieBill]:
        return [parse_bill(j) for j in self._get(f"/accounts/{account_id}/bills")]

    def get_deposits(self, account_id: str) -> list[NessieDeposit]:
        return [parse_deposit(j) for j in self._get(f"/accounts/{account_id}/deposits")]

    def get_purchases(self, account_id: str) -> list[NessiePurchase]:
        return [parse_purchase(j) for j in self._get(f"/accounts/{account_id}/purchases")]


class FakeNessie:
    """In-memory stand-in with the same behavior and shapes (it stores Nessie-shaped JSON and
    reads it back through the same parsers), so tests and keyless runs need no network."""

    def __init__(self) -> None:
        self._n = 0
        self._accounts: dict[str, list[dict]] = {}
        self._bills: dict[str, list[dict]] = {}
        self._deposits: dict[str, list[dict]] = {}
        self._purchases: dict[str, list[dict]] = {}

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"fake-{prefix}-{self._n}"

    def create_customer(self, first_name: str, last_name: str, zip_code: str) -> str:
        cid = self._id("cust")
        self._accounts[cid] = []
        return cid

    def create_account(self, customer_id: str, kind: str, balance: Decimal) -> str:
        aid = self._id("acct")
        self._accounts[customer_id].append(
            {"_id": aid, "type": kind.capitalize(), "balance": str(balance)}
        )
        for store in (self._bills, self._deposits, self._purchases):
            store[aid] = []
        return aid

    def create_bill(self, account_id: str, payee: str, amount: Decimal) -> str:
        bid = self._id("bill")
        self._bills[account_id].append({"_id": bid, "payee": payee, "payment_amount": str(amount)})
        return bid

    def create_deposit(self, account_id: str, on: date, amount: Decimal, description: str) -> str:
        did = self._id("dep")
        self._deposits[account_id].append(
            {"_id": did, "transaction_date": on.isoformat(), "amount": str(amount)}
        )
        return did

    def create_purchase(self, account_id: str, on: date, amount: Decimal, description: str) -> str:
        pid = self._id("pur")
        self._purchases[account_id].append(
            {"_id": pid, "purchase_date": on.isoformat(), "amount": str(amount), "description": description}
        )
        return pid

    def get_accounts(self, customer_id: str) -> list[NessieAccount]:
        return [parse_account(j) for j in self._accounts.get(customer_id, [])]

    def get_bills(self, account_id: str) -> list[NessieBill]:
        return [parse_bill(j) for j in self._bills.get(account_id, [])]

    def get_deposits(self, account_id: str) -> list[NessieDeposit]:
        return [parse_deposit(j) for j in self._deposits.get(account_id, [])]

    def get_purchases(self, account_id: str) -> list[NessiePurchase]:
        return [parse_purchase(j) for j in self._purchases.get(account_id, [])]
