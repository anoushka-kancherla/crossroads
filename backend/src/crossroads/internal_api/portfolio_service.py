"""The refresh job and the portfolio response (FR-015..FR-018, FR-037).

Refresh runs the engine for every customer at their own default inputs, exactly as the customer sees
them, checks the explanation for each, and stores one row per customer. The dashboard is then built
only from those rows, so its totals reconcile with the individual results.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from ..config import Config
from ..customer_api.paths_service import default_inputs
from ..customer_api.store import CustomerStore
from ..engine.portfolio import CustomerResult, summarize
from ..engine.recommend import evaluate
from ..explain.facts import build_facts
from ..explain.service import ExplainService
from .schemas import KpisOut, PathRowOut, PortfolioResponse, StepRowOut
from .snapshots import SnapshotRow, SnapshotStore

ASSUMPTIONS = [
    "A customer is retained when their recommended path keeps a Toyota Financial Services contract. "
    "Returning the car and walking away does not.",
    "Estimated revenue is Toyota's interest income over five years on the recommended path (the rent "
    "charge, for a lease). It is zero when the customer isn't retained.",
    "Average customer savings is the five-year cost of keeping the current plan minus the cost of the "
    "recommended path, for customers who have a recommendation.",
    "A customer with no affordable path counts as not retained and adds no revenue.",
    "Next steps are sorted into self-service, eligible offer and specialist follow-up by an illustrative "
    "rule for each path, not Toyota policy. Self-service means no specialist or offer is needed.",
    "Every figure comes from the demo customers' own recommendations, using illustrative values.",
]


def refresh_snapshots(
    store: CustomerStore, snapshots: SnapshotStore, cfg: Config, explain: ExplainService, now: datetime | None = None
) -> list[SnapshotRow]:
    now = now or datetime.now(UTC)
    rows: list[SnapshotRow] = []
    for entry in store.list_customers():
        rec = store.get_record(entry.id)
        inp = default_inputs(rec, cfg)
        ev = evaluate(inp, cfg)
        facts, variant = build_facts(inp, ev, cfg)
        explanation = explain.explain(facts, variant)
        by = {o.path: o for o in ev.options}
        chosen = by.get(ev.recommendation.path) if ev.recommendation.path else None
        rows.append(
            SnapshotRow(
                CustomerResult(
                    customer_id=entry.id,
                    path=chosen.path if chosen else None,
                    five_year_cost=chosen.five_year_cost if chosen else None,
                    baseline_cost=by["keep_as_is"].five_year_cost,
                    retained=bool(chosen and chosen.retained),
                    revenue=chosen.revenue if chosen else Decimal(0),
                    explanation_verified=explanation.verified,
                ),
                now,
            )
        )
    snapshots.save(rows)
    return rows


def build_portfolio(rows: list[SnapshotRow]) -> PortfolioResponse:
    p = summarize([r.result for r in rows])
    return PortfolioResponse(
        empty=not rows,
        computed_at=max((r.computed_at for r in rows), default=None),
        customers_total=p.customers_total,
        no_recommendation=p.no_recommendation,
        kpis=KpisOut(
            retained_count=p.retained_count,
            retained_pct=p.retained_pct,
            revenue_total=p.revenue_total,
            avg_savings=p.avg_savings,
            explanations_verified_pct=p.explanations_verified_pct,
        ),
        by_path=[PathRowOut(**vars(row)) for row in p.by_path],
        next_steps=[StepRowOut(**vars(row)) for row in p.next_steps],
        self_service_pct=p.self_service_pct,
        assumptions=ASSUMPTIONS,
    )
