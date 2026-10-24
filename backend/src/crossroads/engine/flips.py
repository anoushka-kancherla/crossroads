"""Counterfactual search: which single input change would flip the recommendation (FR-011)."""

from __future__ import annotations

import math
from decimal import Decimal

from ..config import Config
from .recommend import evaluate
from .schemas import SLIDERS, EngineInputs, Flip

_ORDER = ("miles_per_year", "monthly_budget", "years_to_keep", "financing_rate")


def _grid(name: str, current: Decimal) -> list[Decimal]:
    lo, hi, step = SLIDERS[name]
    if name == "monthly_budget":  # a customer's own default can sit above the standard maximum
        hi = max(hi, Decimal(math.ceil(current / step)) * step)
    n = int((hi - lo) / step)
    return [lo + step * i for i in range(n + 1)]


def _with(inp: EngineInputs, name: str, value: Decimal) -> EngineInputs:
    typed = int(value) if name in ("miles_per_year", "years_to_keep") else value
    return inp.model_copy(update={"scenario": inp.scenario.model_copy(update={name: typed})})


def find_flips(inp: EngineInputs, cfg: Config) -> list[Flip]:
    """For each input, scan its slider range at slider step outward from the current value and
    take the nearest value that makes a different path the recommendation. At most one flip per
    input (omitted when none exists), sorted by smallest relative change. Points where nothing
    would be affordable are skipped: a flip names the path it moves to."""
    cache: dict = {}
    base = evaluate(inp, cfg, cache).recommendation.path
    flips: list[Flip] = []
    for name in _ORDER:
        current = Decimal(str(getattr(inp.scenario, name)))
        if current == 0:
            continue
        candidates = sorted((v for v in _grid(name, current) if v != current), key=lambda v: (abs(v - current), v))
        for value in candidates:
            path = evaluate(_with(inp, name, value), cfg, cache).recommendation.path
            if path is not None and path != base:
                flips.append(
                    Flip(
                        input=name,
                        current=current,
                        threshold=value,
                        to_path=path,
                        relative_change=(abs(value - current) / current).quantize(Decimal("0.001")),
                    )
                )
                break
    return sorted(flips, key=lambda f: (f.relative_change, _ORDER.index(f.input)))
