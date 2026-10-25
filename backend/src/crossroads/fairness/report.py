"""Assemble the fairness report from the scored population, and keep it in memory.

`build_report_from_results` takes the scored customers, so a test can hand it any list. `build_report`
generates and scores the seeded population first. Nothing is stored: the report is a deterministic
computation from fixed seeds, and the cache holds only the report, never an individual row.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from ..config import Config, FairnessConfig
from ..customer_api.store import CustomerRecord
from ..engine import fairness as stats
from ..engine.fairness import Band, BandSummary, GapEstimate, PopulationResult, Verdict
from ..engine.money import fmt_money
from ..engine.schemas import PATH_ORDER
from .bootstrap import bootstrap_interval, gap_seed
from .population import generate_population
from .scoring import score

LIMITS = (
    "Only income is examined. Other characteristics are not covered.",
    "The customers are synthetic. This shows how the engine behaves on this population, not how real "
    "customers are treated.",
    "This is a demonstration of the method, not a legal fair-lending finding.",
)


@dataclass(frozen=True)
class FairnessReport:
    empty: bool
    computed_at: datetime
    cfg: FairnessConfig
    size: int
    loans: int
    leases: int
    description: tuple[str, ...]
    band_defs: tuple[Band, ...]
    bands: tuple[BandSummary, ...]
    path_mix: tuple[tuple[str, int], ...]
    verdict: Verdict | None
    by_type: tuple[GapEstimate, ...]
    limits: tuple[str, ...]


def _estimate(
    scope: str, low: Sequence[Decimal], high: Sequence[Decimal], cfg: FairnessConfig
) -> GapEstimate:
    """The lowest-vs-highest gap and its interval from the given rank lists (rank units in, points out)."""
    if not stats.is_enough(len(low), len(high), cfg.min_choice):
        return stats.make_estimate(scope, len(low), len(high), cfg.min_choice)
    ci = bootstrap_interval(low, high, seed=gap_seed(cfg.bootstrap_seed, scope), resamples=cfg.resamples)
    return stats.make_estimate(
        scope, len(low), len(high), cfg.min_choice, stats.gap_between(list(low), list(high)), ci
    )


def _ranks(results: Sequence[PopulationResult]) -> list[Decimal]:
    return [r for r in (stats.profitability_rank(x) for x in results) if r is not None]


def build_report_from_results(
    results: Sequence[PopulationResult],
    cfg: FairnessConfig,
    records: Sequence[CustomerRecord] = (),
    now: datetime | None = None,
) -> FairnessReport:
    now = now or datetime.now(UTC)
    defs = stats.bands_from(cfg.band_edges)
    loans = sum(r.contract_type == "loan" for r in results)
    if not results:
        return FairnessReport(True, now, cfg, 0, 0, 0, (), defs, (), (), None, (), LIMITS)
    grouped: list[list[PopulationResult]] = [[], [], []]
    for r in results:
        grouped[stats.band_index(r.income, cfg.band_edges)].append(r)
    bands = tuple(stats.summarize_band(b, g) for b, g in zip(defs, grouped, strict=True))
    mix = tuple(
        (p, c) for p in PATH_ORDER if (c := sum(dict(b.path_counts).get(p, 0) for b in bands))
    )
    low, high = grouped[0], grouped[2]
    pooled = _estimate("all", _ranks(low), _ranks(high), cfg)
    by_type = tuple(
        _estimate(
            kind,
            _ranks([r for r in low if r.contract_type == kind]),
            _ranks([r for r in high if r.contract_type == kind]),
            cfg,
        )
        for kind in ("loan", "lease")
    )
    verdict = stats.decide(pooled, cfg.gap_threshold_points, cfg.min_choice, len(low), len(high))
    return FairnessReport(
        False, now, cfg, len(results), loans, len(results) - loans,
        tuple(describe_population(records, cfg)) if records else (),
        defs, bands, mix, verdict, by_type, LIMITS,
    )


def _pct(x: Decimal) -> str:
    return f"{stats.round1(x * 100):f}%"


def describe_population(records: Sequence[CustomerRecord], cfg: FairnessConfig) -> list[str]:
    """Plain lines saying how the population was built and what it looks like, for the limits panel."""
    if not records:
        return []
    n = len(records)
    incomes = sorted(r.income for r in records)
    q1, med, q3 = incomes[n // 4], incomes[n // 2], incomes[(3 * n) // 4]
    idx = [stats.band_index(r.income, cfg.band_edges) for r in records]

    def mean_of(band: int, f: Callable[[CustomerRecord], Decimal]) -> Decimal:
        rows = [f(r) for r, i in zip(records, idx, strict=True) if i == band]
        return sum(rows, Decimal(0)) / len(rows) if rows else Decimal(0)

    bills_lo = mean_of(0, lambda r: r.bills_total / r.income)
    bills_hi = mean_of(2, lambda r: r.bills_total / r.income)
    lease_lo = mean_of(0, lambda r: Decimal(r.contract.type == "lease"))
    lease_hi = mean_of(2, lambda r: Decimal(r.contract.type == "lease"))
    leases = sum(r.contract.type == "lease" for r in records)
    classes = {c: sum(r.vehicle.vehicle_class == c for r in records) for c in ("sedan", "suv", "truck")}
    no_odo = sum(not r.readings for r in records)
    return [
        f"Monthly income: median {fmt_money(med)}, middle half {fmt_money(q1)} to {fmt_money(q3)}, "
        f"range {fmt_money(incomes[0])} to {fmt_money(incomes[-1])}.",
        f"Bills: a fixed base of $1,000 plus 28% of income, with random variation; about {_pct(bills_lo)} "
        f"of income in the lowest band and {_pct(bills_hi)} in the highest.",
        f"Contract type: {n - leases} loans and {leases} leases, drawn independently of income "
        f"(leases are {_pct(lease_lo)} of the lowest band and {_pct(lease_hi)} of the highest).",
        "Payments: 8% to 16% of income.",
        f"Vehicles: {classes['sedan']} sedans, {classes['suv']} SUVs and {classes['truck']} trucks, "
        "drawn independently of income.",
        f"{no_odo} customers ({_pct(Decimal(no_odo) / n)}) have no odometer history.",
        "No market listings are used: values are estimated by depreciation.",
    ]


def build_report(fairness_cfg: FairnessConfig, app_cfg: Config, now: datetime | None = None) -> FairnessReport:
    records = generate_population(fairness_cfg, app_cfg.as_of)
    return build_report_from_results(score(records, app_cfg), fairness_cfg, records, now)


class FairnessService:
    """Computes the report on first use and serves it from memory afterwards; `recompute()` replaces it."""

    def __init__(self, fairness_cfg: FairnessConfig, app_cfg: Config):
        self._fcfg, self._acfg = fairness_cfg, app_cfg
        self._report: FairnessReport | None = None
        self._lock = threading.Lock()

    def get(self) -> FairnessReport:
        with self._lock:
            if self._report is None:
                self._report = build_report(self._fcfg, self._acfg)
            return self._report

    def recompute(self) -> FairnessReport:
        with self._lock:
            self._report = build_report(self._fcfg, self._acfg)
            return self._report
