"""Environment settings (secrets) and the illustrative demo configuration.

Every value in `Config` is illustrative and is labeled "illustrative" wherever it is shown to a
user. Secrets are read only from environment variables (constitution, principle V).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


def _d(x: str) -> Decimal:
    return Decimal(x)


@dataclass(frozen=True)
class Config:
    horizon_months: int = 60
    as_of: date = date(2026, 10, 24)  # the demo clock: the synthetic data is dated as of this day
    buffer: Decimal = _d("300")  # kept free every month (FR-008)
    baseline_miles: int = 13_500  # typical U.S. driver; also the depreciation mileage baseline
    depreciation: Decimal = _d("0.12")  # per year (FR-034)
    per_mile: Decimal = _d("0.12")  # value adjustment per mile above or below the baseline
    value_floor: Decimal = _d("0.10")  # a car is never worth less than this share of today's value
    disposition_fee: Decimal = _d("395")  # waived Toyota-to-Toyota
    replacement_due: Decimal = _d("3000")  # due at signing for the replacement lease
    replacement_monthly: dict[str, Decimal] = field(
        default_factory=lambda: {"sedan": _d("380"), "suv": _d("450"), "truck": _d("520")}
    )
    # Used only to estimate Toyota's rent-charge revenue on the replacement lease (FR-017).
    replacement_cap_cost: dict[str, Decimal] = field(
        default_factory=lambda: {"sedan": _d("28000"), "suv": _d("34000"), "truck": _d("40000")}
    )
    replacement_residual_pct: Decimal = _d("0.60")
    replacement_money_factor: Decimal = _d("0.0025")
    extra_principal_monthly: Decimal = _d("200")  # extra toward principal, or the room left if less
    buyout_term_months: int = 60
    default_financing_rate: Decimal = _d("6.5")  # percent APR


@dataclass(frozen=True)
class Settings:
    database_url: str
    nessie_api_key: str
    serpapi_api_key: str
    gemini_api_key: str
    gemini_model: str
    staff_user: str
    staff_password_hash: str
    session_secret: str
    cookie_secure: bool = False  # set COOKIE_SECURE=true when the site is served over HTTPS


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        database_url=env("DATABASE_URL", "postgresql://crossroads:crossroads@localhost:5432/crossroads"),
        nessie_api_key=env("NESSIE_API_KEY", ""),
        serpapi_api_key=env("SERPAPI_API_KEY", ""),
        gemini_api_key=env("GEMINI_API_KEY", ""),
        gemini_model=env("GEMINI_MODEL", ""),
        staff_user=env("STAFF_USER", ""),
        staff_password_hash=env("STAFF_PASSWORD_HASH", ""),
        session_secret=env("SESSION_SECRET", ""),
        cookie_secure=env("COOKIE_SECURE", "").lower() == "true",
    )


@dataclass(frozen=True)
class FairnessConfig:
    """Settings for the fairness check (feature 002). The bands, threshold and minimum can be set in the
    environment; the seeds, resample count and population size are fixed so the method stays reproducible."""

    population_size: int = 500
    population_seed: int = 20261024
    band_edges: tuple[Decimal, Decimal] = (_d("4500"), _d("6500"))  # monthly income; a boundary joins the higher band
    gap_threshold_points: Decimal = _d("15")
    min_choice: int = 30  # customers with a real choice needed in each compared band
    resamples: int = 1000
    bootstrap_seed: int = 20261025
    confidence: int = 95
    min_band_population: int = 100  # the generator refuses a population with a thinner band


def load_fairness_config(env: Mapping[str, str] | None = None) -> FairnessConfig:
    """Defaults, overridden by FAIRNESS_BAND_EDGES, FAIRNESS_GAP_THRESHOLD and FAIRNESS_MIN_CHOICE.
    An empty value means "not set". An invalid value raises a ValueError naming the setting."""
    env = os.environ if env is None else env

    def raw(name: str) -> str | None:
        return (env.get(name) or "").strip() or None

    def bad(name: str, why: str) -> ValueError:
        return ValueError(f"{name} {why}")

    out: dict = {}
    if (v := raw("FAIRNESS_BAND_EDGES")) is not None:
        try:
            edges = tuple(Decimal(x.strip()) for x in v.split(","))
        except ArithmeticError:
            raise bad("FAIRNESS_BAND_EDGES", f"must be two comma-separated monthly incomes, got {v!r}") from None
        if len(edges) != 2 or not (0 < edges[0] < edges[1]):
            raise bad("FAIRNESS_BAND_EDGES", f"must be two increasing monthly incomes above 0, got {v!r}")
        out["band_edges"] = edges
    if (v := raw("FAIRNESS_GAP_THRESHOLD")) is not None:
        try:
            t = Decimal(v)
        except ArithmeticError:
            raise bad("FAIRNESS_GAP_THRESHOLD", f"must be a number of points above 0, got {v!r}") from None
        if not t.is_finite() or t <= 0:
            raise bad("FAIRNESS_GAP_THRESHOLD", f"must be a number of points above 0, got {v!r}")
        out["gap_threshold_points"] = t
    if (v := raw("FAIRNESS_MIN_CHOICE")) is not None:
        if not v.isdigit() or int(v) < 1:
            raise bad("FAIRNESS_MIN_CHOICE", f"must be a whole number, at least 1, got {v!r}")
        out["min_choice"] = int(v)
    return FairnessConfig(**out)
