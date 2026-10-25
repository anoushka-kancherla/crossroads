"""GET /api/customers/{id}/payments: the payment history split into principal and interest (FR-040)."""

from decimal import Decimal as D

from fastapi.testclient import TestClient

from crossroads.customer_api.main import create_app
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles, payment_history

PROFILES = {p.id: p for p in generate_profiles()}
client = TestClient(create_app(store=InMemoryStore(list(PROFILES.values()))))


def payments(cid):
    r = client.get(f"/api/customers/{cid}/payments")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_lease_customer_gets_one_row_per_payment_made_oldest_first():
    data = payments("cust_01")
    c = PROFILES["cust_01"].contract
    assert data["kind"] == "lease" and len(data["months"]) == c.term_months - c.months_left
    months = [m["month"] for m in data["months"]]
    assert months == sorted(months) and len(set(months)) == len(months)
    assert all(len(m) == 7 and m[4] == "-" for m in months)


def test_every_month_splits_exactly_into_principal_and_interest():
    for cid in PROFILES:
        for m in payments(cid)["months"]:
            assert D(m["principal"]) + D(m["interest"]) == D(m["amount"]), (cid, m)


def test_a_leases_amount_is_the_contract_payment_and_its_rent_charge_is_level():
    lease = payments("cust_01")["months"]
    assert {m["amount"] for m in lease} == {f"{PROFILES['cust_01'].contract.monthly_payment:.2f}"}
    assert len({m["interest"] for m in lease}) == 1, "a lease's rent charge is the same every month"


def test_a_loans_interest_falls_as_it_is_paid_down():
    loan = payments("cust_07")
    assert loan["kind"] == "loan"
    interest = [D(m["interest"]) for m in loan["months"]]
    assert interest[0] > interest[-1]


def test_the_figures_are_the_seeded_payment_history_summed_by_month():
    for cid, p in PROFILES.items():
        expected = {}
        for on, amount, principal, interest in payment_history(p):
            k = on.strftime("%Y-%m")
            a, pr, i = expected.get(k, (D(0), D(0), D(0)))
            expected[k] = (a + amount, pr + principal, i + interest)
        got = {m["month"]: (D(m["amount"]), D(m["principal"]), D(m["interest"])) for m in payments(cid)["months"]}
        assert got == {k: tuple(v.quantize(D("0.01")) for v in t) for k, t in expected.items()}, cid


def test_an_unknown_customer_is_a_404():
    assert client.get("/api/customers/nobody/payments").status_code == 404


def test_no_figure_is_a_float():
    for m in payments("cust_07")["months"]:
        assert all(isinstance(m[k], str) for k in ("amount", "principal", "interest"))
