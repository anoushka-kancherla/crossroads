"""Pure statistics for the fairness check (feature 002): income bands, the profitability rank, band
summaries and the verdict. Exact Decimal arithmetic only, with no randomness, clock or I/O (constitution,
principle II). The seeded population and the bootstrap live in `crossroads.fairness`, not here.

The steering measure is where the recommended path ranks among the customer's own affordable options by
Toyota's 5-year interest income: 0 for the least profitable, 1 for the most, 0.5 for a tie.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from .money import ZERO, cents, fmt_money
from .schemas import PATH_ORDER

Outcome = Literal["no_evidence", "possible_steering", "not_enough"]
BAND_KEYS = ("lower", "middle", "higher")
_HALF = Decimal("0.5")
_TENTH = Decimal("0.1")
_HUNDRED = Decimal(100)


def round1(x: Decimal) -> Decimal:
    """One decimal place, half up: the value a reviewer reads is the value that decides."""
    return x.quantize(_TENTH, ROUND_HALF_UP)


def _num(x: Decimal) -> str:
    """A threshold or figure as plain text: 15 not 15.0, 12.5 as 12.5."""
    return format(x.normalize(), "f")


# --- income bands -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Band:
    key: str
    label: str
    low: Decimal | None  # inclusive; None for the lowest band
    high: Decimal | None  # exclusive; None for the highest band


def _upto(edge: Decimal) -> str:
    """The last whole amount below an edge: 6,499 for 6,500."""
    return fmt_money(edge - 1) if edge == edge.to_integral_value() else f"${edge - Decimal('0.01'):,.2f}"


def bands_from(edges: tuple[Decimal, Decimal]) -> tuple[Band, Band, Band]:
    a, b = edges
    return (
        Band("lower", f"Under {fmt_money(a)} a month", None, a),
        Band("middle", f"{fmt_money(a)} to {_upto(b)} a month", a, b),
        Band("higher", f"{fmt_money(b)} or more a month", b, None),
    )


def band_index(income: Decimal, edges: tuple[Decimal, Decimal]) -> int:
    """0, 1 or 2. A customer exactly on an edge belongs to the higher band."""
    return sum(income >= e for e in edges)


# --- one customer's result ----------------------------------------------------------------------------


@dataclass(frozen=True)
class PopulationResult:
    """What the engine recommended for one customer. `affordable_revenues` holds Toyota's 5-year interest
    income for every affordable option, the recommended one included."""

    income: Decimal
    contract_type: Literal["loan", "lease"]
    recommended_path: str | None
    recommended_revenue: Decimal
    affordable_revenues: tuple[Decimal, ...]

    @property
    def n_affordable(self) -> int:
        return len(self.affordable_revenues)

    @property
    def has_recommendation(self) -> bool:
        return self.recommended_path is not None and self.n_affordable >= 1

    @property
    def has_choice(self) -> bool:
        return self.has_recommendation and self.n_affordable >= 2


def profitability_rank(r: PopulationResult) -> Decimal | None:
    """(options earning Toyota less + half the other options that tie) / (n - 1); None without a real choice."""
    if not r.has_choice:
        return None
    below = sum(1 for v in r.affordable_revenues if v < r.recommended_revenue)
    tied = sum(1 for v in r.affordable_revenues if v == r.recommended_revenue) - 1
    return (Decimal(below) + _HALF * tied) / (r.n_affordable - 1)


def is_most_profitable(r: PopulationResult) -> bool:
    return r.has_recommendation and r.recommended_revenue >= max(r.affordable_revenues)


def given_up(r: PopulationResult) -> Decimal:
    """Interest income Toyota would have earned from the most profitable option over the recommended one."""
    return max(ZERO, max(r.affordable_revenues) - r.recommended_revenue)


# --- a band's summary ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class BandSummary:
    key: str
    label: str
    customers: int
    with_recommendation: int
    no_affordable: int
    path_counts: tuple[tuple[str, int], ...]
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


def _mean(values: list[Decimal]) -> Decimal | None:
    return sum(values, ZERO) / len(values) if values else None


def summarize_band(band: Band, results: list[PopulationResult]) -> BandSummary:
    rec = [r for r in results if r.has_recommendation]
    choice = [r for r in rec if r.has_choice]
    ranks = [profitability_rank(r) for r in choice]
    counts = {p: sum(1 for r in rec if r.recommended_path == p) for p in PATH_ORDER}
    avg_rev = _mean([r.recommended_revenue for r in rec])
    avg_rank = _mean([x for x in ranks if x is not None])
    avg_given = _mean([given_up(r) for r in choice])
    n = len(results)
    avg_opts = _mean([Decimal(r.n_affordable) for r in results])
    return BandSummary(
        key=band.key,
        label=band.label,
        customers=n,
        with_recommendation=len(rec),
        no_affordable=n - len(rec),
        path_counts=tuple((p, c) for p, c in counts.items() if c),
        avg_revenue=None if avg_rev is None else cents(avg_rev),
        avg_revenue_n=len(rec),
        with_choice=len(choice),
        single_option=len(rec) - len(choice),
        avg_rank_pct=None if avg_rank is None else round1(avg_rank * _HUNDRED),
        avg_rank_n=len(choice),
        most_profitable_count=sum(1 for r in choice if is_most_profitable(r)),
        avg_given_up=None if avg_given is None else cents(avg_given),
        avg_affordable_options=None if avg_opts is None else round1(avg_opts),
        no_affordable_share_pct=None if n == 0 else round1(Decimal(n - len(rec)) * _HUNDRED / n),
    )


# --- the gap and the verdict --------------------------------------------------------------------------


@dataclass(frozen=True)
class GapEstimate:
    """Lowest band minus highest band, in percentage points (displayed values, one decimal). The figures are
    None when either compared band lacks `min_choice` customers with a real choice (`enough` False)."""

    scope: str
    enough: bool
    lowest_n: int
    highest_n: int
    gap_points: Decimal | None = None
    ci_low: Decimal | None = None
    ci_high: Decimal | None = None


def is_enough(lowest_n: int, highest_n: int, min_choice: int) -> bool:
    return lowest_n >= min_choice and highest_n >= min_choice


def make_estimate(
    scope: str,
    lowest_n: int,
    highest_n: int,
    min_choice: int,
    gap: Decimal | None = None,
    ci: tuple[Decimal, Decimal] | None = None,
) -> GapEstimate:
    """Build a GapEstimate from figures in rank units (0 to 1), converting once to points."""
    if not is_enough(lowest_n, highest_n, min_choice) or gap is None or ci is None:
        return GapEstimate(scope, False, lowest_n, highest_n)
    return GapEstimate(
        scope, True, lowest_n, highest_n,
        round1(gap * _HUNDRED), round1(ci[0] * _HUNDRED), round1(ci[1] * _HUNDRED),
    )


def gap_between(low_ranks: list[Decimal], high_ranks: list[Decimal]) -> Decimal:
    """Mean of the lowest band minus mean of the highest band, in rank units."""
    return sum(low_ranks, ZERO) / len(low_ranks) - sum(high_ranks, ZERO) / len(high_ranks)


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    sentence: str
    interval_note: str | None
    gap_points: Decimal | None
    ci_low: Decimal | None
    ci_high: Decimal | None
    lowest_n: int
    highest_n: int


def _interval_note(outcome: Outcome, ci_low: Decimal, ci_high: Decimal, threshold: Decimal) -> str | None:
    t = _num(threshold)
    if outcome == "no_evidence" and ci_high > threshold:
        return f"The data cannot rule out a gap beyond the {t}-point threshold."
    if outcome == "possible_steering":
        if ci_low <= threshold:
            return f"The data cannot confirm the gap is beyond the {t}-point threshold."
        return f"The whole interval is beyond the {t}-point threshold."
    return None


def decide(
    pooled: GapEstimate,
    threshold: Decimal,
    min_choice: int,
    lowest_customers: int | None = None,
    highest_customers: int | None = None,
) -> Verdict:
    """The verdict: `not_enough` unless both compared bands have `min_choice` customers with a real choice;
    else `possible_steering` when the displayed gap is above the threshold, else `no_evidence`. Fixed text with
    the figures filled in: never softened, never written by a model."""
    n_low, n_high = pooled.lowest_n, pooled.highest_n
    if not pooled.enough or pooled.gap_points is None or pooled.ci_low is None or pooled.ci_high is None:
        if lowest_customers == 0 or highest_customers == 0:
            text = (
                "Not enough customers to tell: there is nothing to compare, "
                "because every customer falls in one income band."
            )
        else:
            text = (
                f"Not enough customers to tell: the comparison needs at least {min_choice} customers with a "
                f"real choice in both the lowest-income band ({n_low}) and the highest-income band ({n_high})."
            )
        return Verdict("not_enough", text, None, None, None, None, n_low, n_high)
    gap, lo, hi = pooled.gap_points, pooled.ci_low, pooled.ci_high
    interval = f"95% interval {lo:f} to {hi:f}, from {n_low} and {n_high} customers with a real choice"
    t = _num(threshold)
    if gap > threshold:
        outcome: Outcome = "possible_steering"
        text = (
            "Possible steering of lower-income customers toward paths that earn Toyota more interest, to be "
            f"reviewed: the lowest-income band's recommendations rank {gap:f} points higher than the "
            f"highest-income band's, more than the {t}-point threshold ({interval})."
        )
    else:
        outcome = "no_evidence"
        if gap == 0:
            how = "the same as the highest-income band's"
        else:
            how = f"{abs(gap):f} points {'higher' if gap > 0 else 'lower'} than the highest-income band's"
        text = (
            "No evidence that lower-income customers are steered toward paths that earn Toyota more interest: "
            f"the lowest-income band's recommendations rank {how} ({interval})."
        )
    return Verdict(outcome, text, _interval_note(outcome, lo, hi, threshold), gap, lo, hi, n_low, n_high)
