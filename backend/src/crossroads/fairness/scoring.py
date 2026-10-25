"""Score a population with the recommendation engine, each customer at their own default inputs, exactly
as the customer app does. No network and no key."""

from __future__ import annotations

from collections.abc import Iterable

from ..config import Config
from ..customer_api.paths_service import default_inputs
from ..customer_api.store import CustomerRecord
from ..engine.fairness import PopulationResult
from ..engine.recommend import evaluate


def score(records: Iterable[CustomerRecord], cfg: Config) -> list[PopulationResult]:
    out: list[PopulationResult] = []
    for rec in records:
        ev = evaluate(default_inputs(rec, cfg), cfg)
        affordable = [o for o in ev.options if o.eligible and o.affordable]
        chosen = next((o for o in affordable if o.path == ev.recommendation.path), None)
        out.append(
            PopulationResult(
                income=rec.income,
                contract_type=rec.contract.type,
                recommended_path=None if chosen is None else chosen.path,
                recommended_revenue=chosen.revenue if chosen else rec.income * 0,
                affordable_revenues=tuple(o.revenue for o in affordable),
            )
        )
    return out
