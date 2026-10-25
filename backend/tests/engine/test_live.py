"""The live acceptance figures: pure, from one entry per customer (FR-006, FR-007, FR-013)."""

from __future__ import annotations

import ast
from decimal import Decimal as D
from pathlib import Path

from crossroads.engine import live
from crossroads.engine.live import AcceptanceEntry, live_figures


def entry(cid, retained=True, revenue="1000.00", path="buy_out"):
    return AcceptanceEntry(customer_id=cid, path=path, retained=retained, revenue=D(revenue))


def test_nobody_accepted_gives_no_percent_and_no_income():
    f = live_figures([], customers_total=12, sequence=0)
    assert (f.accepted_customers, f.customers_total, f.retained_customers) == (0, 12, 0)
    assert f.retained_pct is None and f.revenue_total == D(0) and f.sequence == 0


def test_two_of_three_retained_is_67_percent_and_the_income_adds_up():
    es = [entry("a", True, "3572.92"), entry("b", True, "7212.23"), entry("c", False, "0.00", "walk_away")]
    f = live_figures(es, customers_total=12, sequence=5)
    assert (f.accepted_customers, f.retained_customers) == (3, 2)
    assert f.retained_pct == D(67)
    assert f.revenue_total == D(10785)  # 10,785.15 to whole dollars
    assert f.sequence == 5


def test_percent_and_dollars_round_half_up():
    # 1 of 8 retained is 12.5%, which rounds up to 13
    es = [entry("a", True, "0.50")] + [entry(f"x{i}", False, "0.00") for i in range(7)]
    f = live_figures(es, customers_total=12, sequence=8)
    assert f.retained_pct == D(13) and f.revenue_total == D(1)  # 0.50 rounds up to 1


def test_retained_never_exceeds_accepted_and_total_is_passed_through():
    es = [entry("a"), entry("b", False, "0.00")]
    f = live_figures(es, customers_total=12, sequence=2)
    assert f.retained_customers <= f.accepted_customers <= f.customers_total == 12


def test_the_module_has_no_randomness_clock_or_io():
    tree = ast.parse(Path(live.__file__).read_text())
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"random", "datetime", "time", "os", "socket", "requests", "httpx"}
