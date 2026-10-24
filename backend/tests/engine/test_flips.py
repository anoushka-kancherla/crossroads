"""Counterfactual search: one input at a time, nearest change that flips the recommendation."""

import time
from decimal import Decimal as D

from crossroads.engine.flips import _grid, _with, find_flips
from crossroads.engine.recommend import evaluate


def test_every_flip_changes_the_recommendation_to_the_named_path(make_lease, cfg):
    inp = make_lease()
    base = evaluate(inp, cfg).recommendation.path
    flips = find_flips(inp, cfg)
    assert flips, "this customer has at least one flip"
    for f in flips:
        assert f.to_path != base
        after = evaluate(_with(inp, f.input, f.threshold), cfg).recommendation.path
        assert after == f.to_path


def test_at_most_one_flip_per_input(make_lease, make_loan, cfg):
    for inp in (make_lease(), make_loan()):
        names = [f.input for f in find_flips(inp, cfg)]
        assert len(names) == len(set(names))


def test_flips_are_sorted_by_smallest_relative_change(make_lease, make_loan, cfg):
    for inp in (make_lease(), make_loan()):
        changes = [f.relative_change for f in find_flips(inp, cfg)]
        assert changes == sorted(changes)


def test_the_flip_is_the_nearest_grid_value_that_changes_the_path(make_lease, cfg):
    inp = make_lease()
    base = evaluate(inp, cfg).recommendation.path
    for f in find_flips(inp, cfg):
        nearer = [
            v
            for v in _grid(f.input, f.current)
            if v != f.current and abs(v - f.current) < abs(f.threshold - f.current)
        ]
        for v in nearer:
            path = evaluate(_with(inp, f.input, v), cfg).recommendation.path
            assert path in (base, None), (f.input, v)


def test_relative_change_is_the_distance_over_the_current_value(make_lease, cfg):
    for f in find_flips(make_lease(), cfg):
        assert f.relative_change == (abs(f.threshold - f.current) / f.current).quantize(D("0.001"))


def test_thresholds_sit_on_the_slider_grid(make_lease, make_loan, cfg):
    for inp in (make_lease(), make_loan()):
        for f in find_flips(inp, cfg):
            assert f.threshold in _grid(f.input, f.current)


def test_evaluating_and_searching_stays_well_inside_the_time_budget(make_lease, make_loan, cfg):
    # SC-004 targets 1 s; the test allows 2 s so a slow CI machine does not make it flaky.
    for inp in (make_lease(), make_loan()):
        start = time.perf_counter()
        evaluate(inp, cfg)
        find_flips(inp, cfg)
        assert time.perf_counter() - start < 2.0
