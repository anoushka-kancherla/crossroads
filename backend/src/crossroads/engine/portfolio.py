"""Portfolio figures for the Toyota business view (FR-015..FR-018, FR-022, FR-037).

Pure functions over one result per customer, each taken from the same engine run the customer sees,
so the business numbers reconcile exactly with the individual results (FR-018, SC-006).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .money import ZERO, whole
from .schemas import PATH_LABELS, PATH_ORDER, PathId


@dataclass(frozen=True)
class CustomerResult:
    """One customer's recommendation at their default inputs."""

    customer_id: str
    path: PathId | None  # None when no path is affordable
    five_year_cost: Decimal | None  # of the recommended path
    baseline_cost: Decimal  # of "keep as is": the doing-nothing baseline
    retained: bool  # the recommended path keeps a Toyota contract
    revenue: Decimal  # Toyota's 5-year interest income on that path; zero when not retained
    explanation_verified: bool  # the explanation passed the number check


@dataclass(frozen=True)
class PathRow:
    path: PathId
    label: str
    customers: int
    share_pct: Decimal
    stays_with_toyota: bool
    stays_label: str
    revenue: Decimal


@dataclass(frozen=True)
class Portfolio:
    customers_total: int
    retained_count: int
    retained_pct: Decimal
    revenue_total: Decimal
    avg_savings: Decimal
    explanations_verified_pct: Decimal
    no_recommendation: int
    by_path: list[PathRow]


def pct(part: int, total: int) -> Decimal:
    """A whole percent, rounded half up."""
    if total == 0:
        return ZERO
    return (Decimal(part) * 100 / Decimal(total)).quantize(Decimal(1), ROUND_HALF_UP)


def _stays(path: PathId) -> tuple[bool, str]:
    if path == "walk_away":
        return False, "No"
    return True, "Yes (Toyota loan)" if path == "buy_out" else "Yes"


def summarize(results: list[CustomerResult]) -> Portfolio:
    """Counts, retention, revenue and savings. A customer with nothing affordable is counted as not
    retained, adds no revenue, and is left out of the savings average (there is nothing to compare)."""
    total = len(results)
    with_path = [r for r in results if r.path is not None]
    retained = sum(1 for r in results if r.path is not None and r.retained)

    rows = []
    for path in PATH_ORDER:
        chosen = [r for r in with_path if r.path == path]
        stays, label = _stays(path)
        rows.append(
            PathRow(
                path=path,
                label=PATH_LABELS[path],
                customers=len(chosen),
                share_pct=pct(len(chosen), total),
                stays_with_toyota=stays,
                stays_label=label,
                revenue=sum((r.revenue for r in chosen if r.retained), ZERO),
            )
        )

    savings = [r.baseline_cost - r.five_year_cost for r in with_path]
    return Portfolio(
        customers_total=total,
        retained_count=retained,
        retained_pct=pct(retained, total),
        revenue_total=sum((row.revenue for row in rows), ZERO),
        avg_savings=whole(sum(savings, ZERO) / len(savings)) if savings else ZERO,
        explanations_verified_pct=pct(sum(1 for r in results if r.explanation_verified), total),
        no_recommendation=total - len(with_path),
        by_path=rows,
    )
