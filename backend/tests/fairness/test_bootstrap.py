"""The percentile bootstrap: reproducible, exact on constant samples, and equal to a plain re-implementation."""

from __future__ import annotations

import random
from decimal import Decimal as D

import pytest

from crossroads.fairness.bootstrap import bootstrap_interval, gap_seed


def ranks(*xs):
    return [D(str(x)) for x in xs]


def plain(low, high, seed, n):
    """An independent, naive version of the same method."""
    rng = random.Random(seed)
    gaps = []
    for _ in range(n):
        lo = [low[int(rng.random() * len(low))] for _ in low]
        hi = [high[int(rng.random() * len(high))] for _ in high]
        gaps.append(sum(lo) / len(lo) - sum(hi) / len(hi))
    gaps.sort()
    return gaps


def test_same_inputs_and_seed_give_the_identical_interval():
    low, high = ranks(0.1, 0.5, 0.9, 0.3), ranks(0.2, 0.4, 0.6, 0.8, 1)
    assert bootstrap_interval(low, high, seed=5) == bootstrap_interval(low, high, seed=5)


def test_a_different_seed_gives_a_different_interval():
    low, high = ranks(*[i / 40 for i in range(41)]), ranks(*[(i * 7 % 41) / 40 for i in range(30)])
    assert bootstrap_interval(low, high, seed=5) != bootstrap_interval(low, high, seed=6)


def test_constant_samples():
    assert bootstrap_interval(ranks(0.5, 0.5, 0.5), ranks(0.5, 0.5), seed=1) == (0, 0)
    assert bootstrap_interval(ranks(0.8, 0.8), ranks(0.5, 0.5, 0.5), seed=1) == (D("0.3"), D("0.3"))


def test_the_interval_holds_the_observed_gap_for_a_large_symmetric_sample():
    low = ranks(*[i / 100 for i in range(0, 101, 2)])  # mean 0.5
    high = ranks(*[i / 100 for i in range(0, 101, 4)])  # mean 0.5
    lo, hi = bootstrap_interval(low, high, seed=9)
    assert lo < 0 < hi


def test_the_percentile_indexes_for_1000_are_24_and_974():
    low, high = ranks(0.1, 0.5, 0.9, 0.3), ranks(0.2, 0.4, 0.6, 0.8)
    gaps = plain(low, high, 11, 1000)
    assert bootstrap_interval(low, high, seed=11) == (gaps[24], gaps[974])


def test_a_hand_computed_example_with_ten_resamples():
    low, high = ranks(0, 1, 0.5, 0.25), ranks(0.5, 0.5, 0, 1)
    gaps = plain(low, high, 3, 10)
    # ten resamples: ceil(0.25) - 1 = 0 and ceil(9.75) - 1 = 9, the smallest and the largest gap;
    # the literal below was recorded from a run that matched the plain version above
    assert bootstrap_interval(low, high, seed=3, resamples=10) == (gaps[0], gaps[9])
    assert bootstrap_interval(low, high, seed=3, resamples=10) == (D("-0.250"), D("0.4375"))


def test_it_refuses_an_empty_sample_and_does_not_mutate_its_input():
    with pytest.raises(ValueError, match="at least one"):
        bootstrap_interval([], ranks(0.5), seed=1)
    low, high = ranks(0.3, 0.1), ranks(0.9)
    before = (list(low), list(high))
    bootstrap_interval(low, high, seed=1)
    assert (low, high) == before


def test_each_scope_gets_its_own_fixed_seed():
    seeds = {gap_seed(20261025, s) for s in ("all", "loan", "lease")}
    assert len(seeds) == 3 and gap_seed(20261025, "loan") == gap_seed(20261025, "loan")
