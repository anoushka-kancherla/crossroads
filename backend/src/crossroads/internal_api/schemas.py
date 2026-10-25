"""Internal API models. Money and percentages travel as strings, like the customer API."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from ..engine.schemas import PATH_LABELS
from ..fairness.report import FairnessReport

PathName = Literal[
    "keep_as_is", "buy_out", "return_lease_new", "trade_in_early", "refinance", "extra_principal", "walk_away"
]


NextStepName = Literal["self_service", "eligible_offer", "specialist_follow_up"]


class LoginRequest(BaseModel):
    username: str = Field(max_length=256)
    password: str = Field(max_length=1024)


class SessionOut(BaseModel):
    user: str


class KpisOut(BaseModel):
    retained_count: int
    retained_pct: Decimal
    revenue_total: Decimal
    avg_savings: Decimal
    explanations_verified_pct: Decimal


class PathRowOut(BaseModel):
    path: PathName
    label: str
    customers: int
    share_pct: Decimal
    stays_with_toyota: bool
    stays_label: str
    revenue: Decimal
    next_step: NextStepName
    next_step_label: str


class StepRowOut(BaseModel):
    step: NextStepName
    label: str
    customers: int
    share_pct: Decimal


class PortfolioResponse(BaseModel):
    empty: bool
    computed_at: datetime | None
    customers_total: int
    no_recommendation: int
    kpis: KpisOut
    by_path: list[PathRowOut]
    next_steps: list[StepRowOut]
    self_service_pct: Decimal
    assumptions: list[str]


# --- fairness check (feature 002): band-level figures only, never an individual customer -----------------

OutcomeName = Literal["no_evidence", "possible_steering", "not_enough"]


class PathCountOut(BaseModel):
    path: PathName
    label: str
    customers: int


class PopulationOut(BaseModel):
    size: int
    seed: int
    description: list[str]
    loans: int
    leases: int


class ThresholdsOut(BaseModel):
    gap_points: Decimal
    min_choice: int
    resamples: int
    confidence_pct: int
    bootstrap_seed: int


class BandOut(BaseModel):
    key: Literal["lower", "middle", "higher"]
    label: str
    customers: int
    with_recommendation: int
    no_affordable: int
    path_counts: list[PathCountOut]
    avg_revenue: Decimal | None
    avg_revenue_n: int
    with_choice: int
    single_option: int
    avg_rank_pct: Decimal | None
    avg_rank_n: int
    most_profitable_count: int
    avg_given_up: Decimal | None
    avg_affordable_options: Decimal | None
    no_affordable_share_pct: Decimal | None


class VerdictOut(BaseModel):
    outcome: OutcomeName
    sentence: str
    interval_note: str | None
    gap_points: Decimal | None
    ci_low: Decimal | None
    ci_high: Decimal | None
    lowest_n: int
    highest_n: int


class GapOut(BaseModel):
    scope: Literal["loan", "lease"]
    enough: bool
    lowest_n: int
    highest_n: int
    gap_points: Decimal | None
    ci_low: Decimal | None
    ci_high: Decimal | None


class FairnessResponse(BaseModel):
    empty: bool
    computed_at: datetime
    population: PopulationOut
    thresholds: ThresholdsOut
    bands: list[BandOut]
    path_mix: list[PathCountOut]
    verdict: VerdictOut | None
    by_type: list[GapOut]
    limits: list[str]


def fairness_response(r: FairnessReport) -> FairnessResponse:
    """The report as the API returns it: fixed fields, exact decimals, nothing about any one customer."""

    def counts(pairs) -> list[PathCountOut]:
        return [PathCountOut(path=p, label=PATH_LABELS[p], customers=c) for p, c in pairs]

    return FairnessResponse(
        empty=r.empty,
        computed_at=r.computed_at,
        population=PopulationOut(
            size=r.size, seed=r.cfg.population_seed, description=list(r.description), loans=r.loans,
            leases=r.leases,
        ),
        thresholds=ThresholdsOut(
            gap_points=r.cfg.gap_threshold_points, min_choice=r.cfg.min_choice, resamples=r.cfg.resamples,
            confidence_pct=r.cfg.confidence, bootstrap_seed=r.cfg.bootstrap_seed,
        ),
        bands=[BandOut(**{**dataclasses.asdict(b), "path_counts": counts(b.path_counts)}) for b in r.bands],
        path_mix=counts(r.path_mix),
        verdict=None if r.verdict is None else VerdictOut(**dataclasses.asdict(r.verdict)),
        by_type=[GapOut(**dataclasses.asdict(g)) for g in r.by_type],
        limits=list(r.limits),
    )
