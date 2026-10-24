"""Environment settings (secrets) and the illustrative demo configuration.

Every value in `Config` is illustrative and is labeled "illustrative" wherever it is shown to a
user. Secrets are read only from environment variables (constitution, principle V).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal


def _d(x: str) -> Decimal:
    return Decimal(x)


@dataclass(frozen=True)
class Config:
    horizon_months: int = 60
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
    )
