"""GET /api/internal/fairness: sign-in, shape, states, reconciliation and refresh (FR-001, 015..018, 022, 023)."""

from __future__ import annotations

import dataclasses
import json
import secrets

import pytest
from fastapi.testclient import TestClient

from crossroads.config import Config, FairnessConfig, Settings
from crossroads.fairness.report import FairnessService
from crossroads.internal_api.auth import hash_password
from crossroads.internal_api.main import create_app
from crossroads.internal_api.snapshots import InMemorySnapshots
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

URL = "/api/internal"
PASSWORD = secrets.token_urlsafe(18)  # fresh each run, never written to a file
SETTINGS = Settings("", "", "", "", "", "staff", hash_password(PASSWORD), secrets.token_urlsafe(32))
PROFILES = generate_profiles()


def client(*, signed_in=True, **kw) -> TestClient:
    app = create_app(settings=SETTINGS, store=InMemoryStore(PROFILES), snapshots=InMemorySnapshots(), **kw)
    c = TestClient(app)
    if signed_in:
        assert c.post(f"{URL}/login", json={"username": "staff", "password": PASSWORD}).status_code == 204
    return c


@pytest.fixture(scope="module")
def body():
    return client().get(f"{URL}/fairness").json()


def test_no_session_means_401_and_no_figures():
    r = client(signed_in=False).get(f"{URL}/fairness")
    assert r.status_code == 401 and r.json() == {"detail": "Please sign in."}


def test_the_shape(body):
    assert body["empty"] is False and body["computed_at"]
    assert [b["key"] for b in body["bands"]] == ["lower", "middle", "higher"]
    assert body["bands"][0]["label"] == "Under $4,500 a month"
    assert body["verdict"]["outcome"] in {"no_evidence", "possible_steering", "not_enough"}
    assert isinstance(body["verdict"]["sentence"], str) and body["verdict"]["sentence"]
    assert body["thresholds"] == {
        "gap_points": "15", "min_choice": 30, "resamples": 1000, "confidence_pct": 95, "bootstrap_seed": 20261025
    }
    assert body["population"]["size"] == 500 and body["population"]["seed"] == 20261024
    assert body["population"]["loans"] + body["population"]["leases"] == 500
    assert body["limits"] and body["population"]["description"]
    # exact decimals travel as strings, counts as integers
    band = body["bands"][0]
    assert isinstance(band["avg_rank_pct"], str) and isinstance(band["customers"], int)
    assert isinstance(body["verdict"]["gap_points"], str)


def test_the_counts_reconcile(body):
    assert sum(b["customers"] for b in body["bands"]) == body["population"]["size"] == 500
    mix = {m["path"]: m["customers"] for m in body["path_mix"]}
    for b in body["bands"]:
        assert b["with_recommendation"] + b["no_affordable"] == b["customers"]
        assert sum(p["customers"] for p in b["path_counts"]) == b["with_recommendation"]
        assert b["with_choice"] + b["single_option"] == b["with_recommendation"]
    for path, n in mix.items():
        assert n == sum(p["customers"] for b in body["bands"] for p in b["path_counts"] if p["path"] == path)


def test_by_type_lists_loan_then_lease(body):
    assert [g["scope"] for g in body["by_type"]] == ["loan", "lease"]
    for g in body["by_type"]:
        if g["enough"]:
            assert g["gap_points"] is not None and g["ci_low"] is not None and g["ci_high"] is not None
        else:
            assert g["gap_points"] is None and g["ci_low"] is None and g["ci_high"] is None


def test_no_individual_customer_appears(body):
    text = json.dumps(body)
    assert "pop_" not in text and "cust_" not in text
    keys = set()

    def walk(x):
        if isinstance(x, dict):
            keys.update(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(body)
    assert not keys & {"id", "income", "customer_id", "name", "customers_list"}


def test_a_failing_computation_is_a_503_with_nothing_partial():
    class Broken:
        def get(self):
            raise RuntimeError("boom with /secret/path")

        def recompute(self):
            raise RuntimeError("boom")

    r = client(fairness=Broken()).get(f"{URL}/fairness")
    assert r.status_code == 503
    assert r.json() == {"detail": "We couldn't work out the fairness figures right now."}


def test_a_population_of_zero_is_the_empty_state():
    svc = FairnessService(dataclasses.replace(FairnessConfig(), population_size=0), Config())
    data = client(fairness=svc).get(f"{URL}/fairness").json()
    assert data["empty"] is True and data["bands"] == [] and data["by_type"] == [] and data["path_mix"] == []
    assert data["verdict"] is None and data["population"]["size"] == 0


def test_the_second_call_is_served_from_the_cache():
    c = client()
    first = c.get(f"{URL}/fairness").json()
    assert c.get(f"{URL}/fairness").json() == first


def test_an_invalid_setting_stops_the_app_with_a_message_naming_it(monkeypatch):
    monkeypatch.setenv("FAIRNESS_GAP_THRESHOLD", "0")
    with pytest.raises(ValueError, match="FAIRNESS_GAP_THRESHOLD"):
        create_app(settings=SETTINGS, store=InMemoryStore(PROFILES), snapshots=InMemorySnapshots())


def test_the_environment_settings_reach_the_report(monkeypatch):
    monkeypatch.setenv("FAIRNESS_GAP_THRESHOLD", "12.5")
    monkeypatch.setenv("FAIRNESS_MIN_CHOICE", "40")
    data = client().get(f"{URL}/fairness").json()
    assert data["thresholds"]["gap_points"] == "12.5" and data["thresholds"]["min_choice"] == 40


# --- refresh (FR-015, FR-022) ---------------------------------------------------------------------------


def _figures(d):
    return {k: v for k, v in d.items() if k != "computed_at"}


def test_refresh_recomputes_the_fairness_report_with_identical_figures():
    c = client()
    before = c.get(f"{URL}/fairness").json()
    assert c.post(f"{URL}/portfolio/refresh").status_code == 200
    after = c.get(f"{URL}/fairness").json()
    assert after["computed_at"] > before["computed_at"]
    assert _figures(after) == _figures(before)


def test_a_failing_fairness_recompute_never_breaks_the_portfolio_refresh():
    class RecomputeFails(FairnessService):
        def recompute(self):
            raise RuntimeError("stack trace should stay in the log")

    good = client().post(f"{URL}/portfolio/refresh")
    bad = client(fairness=RecomputeFails(FairnessConfig(), Config())).post(f"{URL}/portfolio/refresh")
    assert bad.status_code == 200
    assert _figures(bad.json()) == _figures(good.json())
    assert "Traceback" not in bad.text and "stack trace" not in bad.text


def test_the_fairness_view_is_read_only():
    c = client()
    portfolio_before = c.post(f"{URL}/portfolio/refresh").json()
    c.get(f"{URL}/fairness")
    assert c.get(f"{URL}/portfolio").json() == portfolio_before
