"""The Overview response: contract summary, mileage, money picture and market value (US1, FR-002..005, FR-032)."""

from collections import defaultdict
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from crossroads.customer_api.main import create_app
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

PROFILES = {p.id: p for p in generate_profiles()}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(store=InMemoryStore(list(PROFILES.values()))))


def overview(client, cid):
    r = client.get(f"/api/customers/{cid}/overview")
    assert r.status_code == 200, r.text
    return r.json()


def test_every_customer_has_a_complete_overview(client):
    for cid in PROFILES:
        data = overview(client, cid)
        assert set(data) == {"customer", "tiles", "mileage", "money", "market_value"}
        assert data["customer"]["id"] == cid


def test_a_lease_overview_matches_the_contract_figures(client):
    t = overview(client, "cust_01")["tiles"]
    assert t["monthly_payment"] == "389.00"
    assert (t["payments_made"], t["payments_total"], t["months_left"]) == (22, 36, 14)
    # buyout = residual 21,450 + 14 remaining payments of 389
    assert t["payoff_or_buyout"] == "26896.00"
    assert t["equity"] == "-4296.00"  # 22,600 market value minus the buyout
    assert t["allowance"] == 36000
    assert t["ends_on"] == str(PROFILES["cust_01"].end_date)


def test_a_loan_overview_has_no_allowance_and_no_overage(client):
    data = overview(client, "cust_07")
    assert data["tiles"]["payoff_or_buyout"] == "12400.00"
    assert data["tiles"]["equity"] == "5200.00"  # 17,600 − 12,400
    assert data["tiles"]["allowance"] is None
    assert data["mileage"]["allowance_per_month"] is None
    # not applicable, so absent rather than shown as zero
    assert data["mileage"]["projection"]["overage_miles"] is None
    assert data["mileage"]["projection"]["overage_fee"] is None


def test_the_money_picture(client):
    m = overview(client, "cust_01")["money"]
    assert (m["checking"], m["savings"]) == ("3100.00", "1800.00")
    assert (m["monthly_income"], m["monthly_bills"]) == ("5200.00", "2650.00")
    assert m["room_for_payment"] == "2250.00"  # income − bills − the $300 buffer


def test_room_for_a_payment_is_never_negative(client):
    for cid in PROFILES:
        assert D(overview(client, cid)["money"]["room_for_payment"]) >= 0


def test_the_projection_is_consistent_with_its_own_figures(client):
    for cid, p in PROFILES.items():
        data = overview(client, cid)
        proj, tiles = data["mileage"]["projection"], data["tiles"]
        months_left = data["customer"]["months_left"]
        assert proj["end_miles"] == round(tiles["miles_driven"] + proj["rate_per_year"] * months_left / 12)
        if p.contract.type == "lease":
            expected = max(0, proj["end_miles"] - tiles["allowance"])
            assert proj["overage_miles"] == expected
            assert D(proj["overage_fee"]) == (D(expected) * p.contract.overage_fee_per_mile).quantize(D("0.01"))


def test_overage_on_a_lease_is_visible(client):
    proj = overview(client, "cust_02")["mileage"]["projection"]  # drives 16,500 a year on a 12,000 allowance
    assert proj["overage_miles"] > 0 and D(proj["overage_fee"]) > 0


def test_the_projection_basis_is_labeled(client):
    assert overview(client, "cust_01")["mileage"]["projection"]["basis"] == "history"
    lease = overview(client, "cust_04")["mileage"]["projection"]  # one reading
    assert lease["basis"] == "allowance" and "lease allowance" in lease["basis_label"]
    loan = overview(client, "cust_11")["mileage"]["projection"]  # a short history
    assert loan["basis"] == "typical_us_driver"
    assert loan["rate_per_year"] == 13500
    assert "illustrative" in loan["basis_label"] and "13,500" in loan["basis_label"]


def test_no_history_means_an_empty_chart_but_a_projection(client):
    data = overview(client, "cust_04")
    assert data["mileage"]["actual_monthly"] == []
    assert len(data["mileage"]["projected_monthly"]) == data["customer"]["months_left"]
    assert data["mileage"]["projected_monthly"][0]["month"] == "2026-11"  # the month after the only reading


def test_the_projected_months_follow_the_last_actual_month(client):
    mileage = overview(client, "cust_01")["mileage"]
    last, first = mileage["actual_monthly"][-1]["month"], mileage["projected_monthly"][0]["month"]
    assert last < first
    rate = mileage["projection"]["rate_per_year"]
    assert {pt["miles"] for pt in mileage["projected_monthly"]} == {round(rate / 12)}


def test_the_lease_allowance_line_is_per_month(client):
    assert overview(client, "cust_01")["mileage"]["allowance_per_month"] == 1000  # 36,000 over 36 months


def test_market_value_from_listings_is_a_labeled_range(client):
    mv = overview(client, "cust_01")["market_value"]
    assert mv["basis"] == "listings"
    assert (mv["low"], mv["median"], mv["high"]) == ("21244.00", "22600.00", "23956.00")
    assert mv["basis_label"] == f"From {mv['n_listings']} local listings"
    assert 6 <= mv["n_listings"] <= 11 and mv["updated_at"]


def test_market_value_without_listings_falls_back_and_says_so(client):
    mv = overview(client, "cust_05")["market_value"]
    assert mv["basis"] == "original_price"
    assert (mv["low"], mv["high"], mv["n_listings"]) == (None, None, 0)
    assert mv["median"] == "16696.06"  # 24,500 × 0.88^3
    assert "illustrative 12% yearly depreciation" in mv["basis_label"]


def test_spending_matches_the_transactions(client):
    p = PROFILES["cust_01"]
    expected = defaultdict(D)
    for on, amount, category in p.transactions:
        expected[(on.strftime("%Y-%m"), category)] += amount
    months = client.get("/api/customers/cust_01/spending").json()["months"]
    got = {(pt["month"], pt["category"]): D(pt["amount"]) for pt in months}
    assert got == dict(expected)
