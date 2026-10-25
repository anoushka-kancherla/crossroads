"""Seeded percentile bootstrap of the lowest-vs-highest band gap (FR-010).

The customers with a real choice in each compared band are resampled with replacement, independently
within each band; each resample's gap is the lowest band's mean rank minus the highest band's. The
interval runs from the 2.5th to the 97.5th percentile of the sorted gaps. Indexes are taken as
`int(random() * n)` from a Mersenne Twister, which does not change between library versions, and the
percentile indexes use integer arithmetic. Everything is in rank units (0 to 1) and exact `Decimal`.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from decimal import Decimal

SCOPES = ("all", "loan", "lease")


def gap_seed(base: int, scope: str) -> int:
    """A fixed seed per gap, so adding or reordering a gap never changes another gap's interval."""
    return base + SCOPES.index(scope) * 1_000_003


def bootstrap_interval(
    low_ranks: Sequence[Decimal], high_ranks: Sequence[Decimal], *, seed: int, resamples: int = 1000
) -> tuple[Decimal, Decimal]:
    """The 95% percentile interval of the gap. With 1,000 resamples the ends are the 25th and 975th
    sorted gaps (indexes 24 and 974); in general `ceil(25n/1000) - 1` and `ceil(975n/1000) - 1`."""
    if not low_ranks or not high_ranks:
        raise ValueError("The bootstrap needs at least one customer with a real choice in each band.")
    rng = random.Random(seed)
    low, high = list(low_ranks), list(high_ranks)
    n_low, n_high = len(low), len(high)
    gaps = []
    for _ in range(resamples):
        a = sum((low[int(rng.random() * n_low)] for _ in range(n_low)), Decimal(0)) / n_low
        b = sum((high[int(rng.random() * n_high)] for _ in range(n_high)), Decimal(0)) / n_high
        gaps.append(a - b)
    gaps.sort()
    lo = -(-25 * resamples // 1000) - 1
    hi = -(-975 * resamples // 1000) - 1
    return gaps[max(0, lo)], gaps[hi]
