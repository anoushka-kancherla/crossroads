"""The assembled report: reconciliation, an independent recomputation, the rigged-population check (SC-007),
per-type gaps, the population description and limits, and timing."""

from __future__ import annotations

import dataclasses
import random
import time
from datetime import UTC, datetime
from decimal import Decimal as D

import pytest

from crossroads.config import Config, FairnessConfig
from crossroads.customer_api.paths_service import default_inputs
from crossroads.engine import fairness as stats
from crossroads.engine.recommend import evaluate
from crossroads.fairness import report as rep
from crossroads.fairness.bootstrap import gap_seed
from crossroads.fairness.population import generate_population
from crossroads.fairness.report import FairnessService, build_report, build_report_from_results

FCFG, ACFG = FairnessConfig(), Config()
INCOME = {0: 3500, 1: 5500, 2: 8000}  # one income inside each band


@pytest.fixture(scope="module")
def built():
    return build_report(FCFG, ACFG)


# --- reconciliation -----------------------------------------------------------------------------------


def test_counts_reconcile(built):
    assert built.size == 500 and sum(b.customers for b in built.bands) == 500
    assert [b.key for b in built.bands] == ["lower", "middle", "higher"]
    for b in built.bands:
        assert b.with_recommendation + b.no_affordable == b.customers
        assert sum(c for _, c in b.path_counts) == b.with_recommendation
        assert b.with_choice + b.single_option == b.with_recommendation
    mix = dict(built.path_mix)
    for p in mix:
        assert mix[p] == sum(dict(b.path_counts).get(p, 0) for b in built.bands)
    assert sum(mix.values()) == sum(b.with_recommendation for b in built.bands)
    assert built.loans + built.leases == 500


def test_two_builds_are_identical_apart_from_the_time(built):
    again = build_report(FCFG, ACFG, now=datetime(2030, 1, 1, tzinfo=UTC))
    assert dataclasses.replace(again, computed_at=built.computed_at) == built


# --- an independent recomputation (its own loop, written apart from the code under test) ---------------


def _independent(kind=None):
    ranks = {0: [], 1: [], 2: []}
    counts = {0: 0, 1: 0, 2: 0}
    for rec in generate_population(FCFG, ACFG.as_of):
        inc = rec.income
        band = 0 if inc < 4500 else (1 if inc < 6500 else 2)
        counts[band] += 1
        ev = evaluate(default_inputs(rec, ACFG), ACFG)
        opts = [o for o in ev.options if o.eligible and o.affordable]
        if ev.recommendation.path is None or len(opts) < 2:
            continue
        if kind and rec.contract.type != kind:
            continue
        mine = next(o for o in opts if o.path == ev.recommendation.path).revenue
        below = sum(o.revenue < mine for o in opts)
        tie = sum(o.revenue == mine for o in opts) - 1
        ranks[band].append((D(below) + D("0.5") * tie) / (len(opts) - 1))
    return ranks, counts


def _plain_interval(low, high, seed):
    rng = random.Random(seed)
    gaps = []
    for _ in range(1000):
        a = [low[int(rng.random() * len(low))] for _ in low]
        b = [high[int(rng.random() * len(high))] for _ in high]
        gaps.append(sum(a) / len(a) - sum(b) / len(b))
    gaps.sort()
    return gaps[24], gaps[974]


def _pts(x):
    return (x * 100).quantize(D("0.1"), "ROUND_HALF_UP")


def test_an_independent_recomputation_matches_every_figure(built):
    ranks, counts = _independent()
    for i, b in enumerate(built.bands):
        assert b.customers == counts[i]
        assert b.avg_rank_n == len(ranks[i])
        assert b.avg_rank_pct == _pts(sum(ranks[i]) / len(ranks[i]))
    low, high = ranks[0], ranks[2]
    lo, hi = _plain_interval(low, high, gap_seed(FCFG.bootstrap_seed, "all"))
    gap = sum(low) / len(low) - sum(high) / len(high)
    v = built.verdict
    assert (v.gap_points, v.ci_low, v.ci_high) == (_pts(gap), _pts(lo), _pts(hi))
    assert (v.lowest_n, v.highest_n) == (len(low), len(high))


@pytest.mark.parametrize("kind", ["loan", "lease"])
def test_per_type_gaps_match_an_independent_recomputation(built, kind):
    ranks, _ = _independent(kind)
    g = next(x for x in built.by_type if x.scope == kind)
    low, high = ranks[0], ranks[2]
    assert (g.lowest_n, g.highest_n) == (len(low), len(high))
    assert g.enough == (len(low) >= 30 and len(high) >= 30)
    if g.enough:
        lo, hi = _plain_interval(low, high, gap_seed(FCFG.bootstrap_seed, kind))
        gap = sum(low) / len(low) - sum(high) / len(high)
        assert (g.gap_points, g.ci_low, g.ci_high) == (_pts(gap), _pts(lo), _pts(hi))


def test_by_type_lists_loan_then_lease(built):
    assert [g.scope for g in built.by_type] == ["loan", "lease"]


# --- hand-built populations --------------------------------------------------------------------------


def hand(rng, band, n, *, top, kind="loan"):
    """n customers in a band, each recommended the most profitable option (top) or the least."""
    out = []
    for _ in range(n):
        revs = sorted(D(rng.randint(100, 5000)) for _ in range(rng.randint(2, 4)))
        if len(set(revs)) < 2:
            revs[-1] += 1
        pick = revs[-1] if top else revs[0]
        out.append(stats.PopulationResult(D(INCOME[band]), kind, "buy_out", pick, tuple(revs)))
    return out


@pytest.mark.parametrize("seed", range(20))
def test_a_rigged_population_is_always_reported_as_possible_steering(seed):
    rng = random.Random(seed)
    rigged = hand(rng, 0, 40, top=True) + hand(rng, 1, 30, top=True) + hand(rng, 2, 45, top=False)
    rng.shuffle(rigged)
    v = build_report_from_results(rigged, FCFG).verdict
    assert v.outcome == "possible_steering"
    assert v.gap_points == D("100.0")


@pytest.mark.parametrize("seed", range(5))
def test_the_reverse_is_no_evidence(seed):
    rng = random.Random(seed)
    results = hand(rng, 0, 40, top=False) + hand(rng, 2, 45, top=True)
    v = build_report_from_results(results, FCFG).verdict
    assert v.outcome == "no_evidence" and v.gap_points == D("-100.0")


def test_29_customers_with_a_choice_is_not_enough():
    rng = random.Random(1)
    v = build_report_from_results(hand(rng, 0, 29, top=True) + hand(rng, 2, 45, top=False), FCFG).verdict
    assert v.outcome == "not_enough" and v.gap_points is None and v.ci_low is None
    assert v.lowest_n == 29


def test_the_per_type_gaps_never_change_the_verdict():
    rng = random.Random(2)
    # pooled gap is large but each type on its own is level, because the loan/lease mix differs by band
    low = hand(rng, 0, 40, top=True, kind="loan") + hand(rng, 0, 40, top=False, kind="lease")
    high = hand(rng, 2, 40, top=True, kind="loan") + hand(rng, 2, 40, top=False, kind="lease")
    assert build_report_from_results(low + high, FCFG).verdict.outcome == "no_evidence"
    both_ways = hand(rng, 0, 40, top=True) + hand(rng, 2, 40, top=False)
    r = build_report_from_results(both_ways, FCFG)
    assert r.verdict.outcome == "possible_steering"
    assert [g.enough for g in r.by_type] == [True, False]  # no lease customers at all


def test_a_type_short_of_the_minimum_shows_no_numbers():
    rng = random.Random(3)
    rs = hand(rng, 0, 40, top=True) + hand(rng, 2, 40, top=False) + hand(rng, 0, 29, top=True, kind="lease")
    rs += hand(rng, 2, 40, top=False, kind="lease")
    lease = next(g for g in build_report_from_results(rs, FCFG).by_type if g.scope == "lease")
    assert not lease.enough and (lease.gap_points, lease.ci_low, lease.ci_high) == (None, None, None)
    assert lease.lowest_n == 29


def test_zero_customers_is_an_empty_report():
    r = build_report_from_results([], FCFG)
    assert r.empty and r.bands == () and r.by_type == () and r.verdict is None and r.path_mix == ()


def test_every_customer_in_one_band_says_there_is_nothing_to_compare():
    rng = random.Random(4)
    v = build_report_from_results(hand(rng, 1, 60, top=True), FCFG).verdict
    assert v.outcome == "not_enough" and "nothing to compare" in v.sentence


# --- description, limits, thresholds ------------------------------------------------------------------


def test_the_population_description():
    lines = rep.describe_population(generate_population(FCFG, ACFG.as_of), FCFG)
    text = " ".join(lines)
    needles = (
        "median $", "middle half", "Bills:", "loans and", "sedans", "SUVs", "trucks", "odometer", "No market listings"
    )
    for needle in needles:
        assert needle in text, needle
    assert rep.describe_population([], FCFG) == []


def test_limits_state_what_the_check_does_not_prove(built):
    text = " ".join(built.limits)
    assert "Only income is examined" in text and "Other characteristics are not covered" in text
    assert "synthetic" in text and "not how real customers are treated" in text
    assert "not a legal fair-lending finding" in text
    assert built.cfg.gap_threshold_points == 15 and built.cfg.min_choice == 30
    assert (built.cfg.resamples, built.cfg.confidence, built.cfg.bootstrap_seed) == (1000, 95, 20261025)
    assert built.band_defs[0].label == "Under $4,500 a month"
    assert built.description, "the population design is on the screen"


# --- the service, timing -----------------------------------------------------------------------------


def test_building_the_whole_report_takes_under_two_seconds():
    start = time.perf_counter()
    build_report(FCFG, ACFG)
    assert time.perf_counter() - start < 2.0


def test_the_service_caches_and_recompute_gives_identical_figures():
    svc = FairnessService(FCFG, ACFG)
    first = svc.get()
    assert svc.get() is first
    again = svc.recompute()
    assert again is not first and again.computed_at >= first.computed_at
    assert dataclasses.replace(again, computed_at=first.computed_at) == first
