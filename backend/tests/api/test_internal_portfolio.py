"""The portfolio and refresh routes (FR-015..FR-018, FR-037, SC-006)."""

import re
import secrets
from datetime import UTC, datetime
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from crossroads.adapters.llm import ExplanationDraft, FakeLLM
from crossroads.config import Config, Settings
from crossroads.customer_api.paths_service import default_inputs
from crossroads.engine.recommend import evaluate
from crossroads.engine.schemas import PATH_ORDER
from crossroads.explain.service import ExplainService
from crossroads.internal_api.auth import hash_password
from crossroads.internal_api.main import create_app
from crossroads.internal_api.portfolio_service import refresh_snapshots
from crossroads.internal_api.snapshots import InMemorySnapshots
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

PROFILES = generate_profiles()
CFG = Config()
URL = "/api/internal"
PASSWORD = secrets.token_urlsafe(18)  # fresh each run, never written to a file
HASH = hash_password(PASSWORD)
SECRET = secrets.token_urlsafe(32)


def signed_in(**kw) -> TestClient:
    settings = Settings("", "", "", "", "", "staff", HASH, SECRET)
    app = create_app(settings=settings, store=InMemoryStore(PROFILES), snapshots=InMemorySnapshots(), **kw)
    client = TestClient(app)
    assert client.post(f"{URL}/login", json={"username": "staff", "password": PASSWORD}).status_code == 204
    return client


def expected():
    out = []
    store = InMemoryStore(PROFILES)
    for p in PROFILES:
        ev = evaluate(default_inputs(store.get_record(p.id), CFG), CFG)
        by = {o.path: o for o in ev.options}
        out.append((ev, by, by.get(ev.recommendation.path) if ev.recommendation.path else None))
    return out


def test_before_any_refresh_the_portfolio_is_an_empty_state_not_an_error():
    data = signed_in().get(f"{URL}/portfolio").json()
    assert data["empty"] is True and data["customers_total"] == 0 and data["computed_at"] is None
    assert [r["path"] for r in data["by_path"]] == list(PATH_ORDER)
    assert data["kpis"]["revenue_total"] == "0"


def test_refresh_computes_every_customer_and_get_returns_the_same_portfolio():
    client = signed_in()
    refreshed = client.post(f"{URL}/portfolio/refresh")
    assert refreshed.status_code == 200
    data = refreshed.json()
    assert data["empty"] is False and data["customers_total"] == 12 and data["computed_at"]
    got = client.get(f"{URL}/portfolio").json()
    assert got == data


def test_the_totals_reconcile_exactly_with_each_customers_own_recommendation():
    client = signed_in()
    data = client.post(f"{URL}/portfolio/refresh").json()
    rows = expected()
    assert sum(r["customers"] for r in data["by_path"]) + data["no_recommendation"] == data["customers_total"] == 12
    assert data["no_recommendation"] == sum(1 for *_, c in rows if c is None)
    assert D(data["kpis"]["revenue_total"]) == sum((c.revenue for *_, c in rows if c and c.retained), D(0))
    assert sum(D(r["revenue"]) for r in data["by_path"]) == D(data["kpis"]["revenue_total"])
    assert data["kpis"]["retained_count"] == sum(1 for *_, c in rows if c and c.retained)
    for row in data["by_path"]:
        assert row["customers"] == sum(1 for *_, c in rows if c and c.path == row["path"])


def test_the_two_extra_kpis_are_present_and_computed(  ):
    k = signed_in().post(f"{URL}/portfolio/refresh").json()["kpis"]
    assert D(k["avg_savings"]) >= 0
    assert k["explanations_verified_pct"] == "100"  # every explanation is the checked template or passed the check
    assert set(k) == {"retained_count", "retained_pct", "revenue_total", "avg_savings", "explanations_verified_pct"}


def test_every_path_row_says_whether_the_customer_stays_with_toyota():
    rows = {r["path"]: r for r in signed_in().post(f"{URL}/portfolio/refresh").json()["by_path"]}
    assert rows["walk_away"]["stays_with_toyota"] is False and rows["walk_away"]["stays_label"] == "No"
    assert rows["buy_out"]["stays_label"] == "Yes (Toyota loan)"


def test_the_response_states_its_assumptions_and_has_no_default_risk_column():
    data = signed_in().post(f"{URL}/portfolio/refresh").json()
    assert len(data["assumptions"]) >= 4
    assert any("retained" in a for a in data["assumptions"]) and any("illustrative" in a for a in data["assumptions"])
    assert not any("risk" in key for key in data["by_path"][0])


GOOD = ExplanationDraft(headline="{path_label} fits", explanation="{path_label} costs {cost_5yr} over {horizon_years}.")
BAD = ExplanationDraft(headline="Save 5000", explanation="It costs 31,200.")


def test_refresh_uses_the_model_when_there_is_one_and_checks_what_it_writes():
    llm = FakeLLM([GOOD])
    client = signed_in(llm=llm)
    data = client.post(f"{URL}/portfolio/refresh").json()
    assert len(llm.prompts) >= 1  # the model was asked
    assert data["kpis"]["explanations_verified_pct"] == "100"


def test_model_text_that_fails_the_check_falls_back_to_the_template_and_still_counts_as_verified():
    llm = FakeLLM([BAD])
    data = signed_in(llm=llm).post(f"{URL}/portfolio/refresh").json()
    assert data["kpis"]["explanations_verified_pct"] == "100"


def test_a_broken_explanation_is_counted_as_not_verified(monkeypatch):
    from crossroads.explain import template

    monkeypatch.setitem(template.BODIES, "normal", "It costs 5 dollars.")  # a defect the check must catch
    client = signed_in()
    data = client.post(f"{URL}/portfolio/refresh").json()
    assert D(data["kpis"]["explanations_verified_pct"]) < 100


def test_a_refresh_rewrites_the_stored_results():
    snaps = InMemorySnapshots()
    store = InMemoryStore(PROFILES)
    t1 = datetime(2026, 1, 1, tzinfo=UTC)
    t2 = datetime(2026, 2, 1, tzinfo=UTC)
    refresh_snapshots(store, snaps, CFG, ExplainService(None), now=t1)
    refresh_snapshots(store, snaps, CFG, ExplainService(None), now=t2)
    rows = snaps.load()
    assert len(rows) == 12 and {r.computed_at for r in rows} == {t2}


def test_no_figure_in_the_portfolio_is_a_float_or_has_a_stray_decimal_point():
    data = signed_in().post(f"{URL}/portfolio/refresh").json()
    for value in [*data["kpis"].values(), *(r["revenue"] for r in data["by_path"])]:
        assert isinstance(value, (str, int)) and (isinstance(value, int) or re.fullmatch(r"-?\d+(\.\d+)?", value))


@pytest.mark.parametrize("path", ["/api/customers", "/api/customers/cust_01/overview", "/api/customers/cust_01/paths"])
def test_the_internal_api_has_no_customer_routes(path):
    assert signed_in().get(path).status_code == 404
