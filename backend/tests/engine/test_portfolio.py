"""Portfolio figures: they reconcile exactly with the individual customer results (FR-015..FR-018, FR-022, SC-006)."""

from decimal import Decimal as D

from crossroads.config import Config
from crossroads.customer_api.paths_service import default_inputs
from crossroads.engine.portfolio import CustomerResult, pct, summarize
from crossroads.engine.recommend import evaluate
from crossroads.engine.schemas import PATH_ORDER
from crossroads.seed.memory import InMemoryStore
from crossroads.seed.profiles import generate_profiles

CFG = Config()
PROFILES = generate_profiles()
STORE = InMemoryStore(PROFILES)


def result(cid, path, cost=None, baseline=10000, retained=True, revenue=0, verified=True):
    return CustomerResult(cid, path, None if cost is None else D(cost), D(baseline), retained, D(revenue), verified)


def real_results():
    out = []
    for p in PROFILES:
        ev = evaluate(default_inputs(STORE.get_record(p.id), CFG), CFG)
        by = {o.path: o for o in ev.options}
        chosen = by.get(ev.recommendation.path) if ev.recommendation.path else None
        out.append((p.id, ev, by, chosen))
    return out


def test_all_seven_paths_are_always_listed_in_the_fixed_order():
    assert [r.path for r in summarize([]).by_path] == list(PATH_ORDER)
    assert [r.path for r in summarize([result("a", "buy_out", 5000)]).by_path] == list(PATH_ORDER)


def test_an_empty_portfolio_is_all_zeros():
    p = summarize([])
    assert (p.customers_total, p.retained_count, p.retained_pct, p.revenue_total, p.avg_savings) == (0, 0, 0, 0, 0)
    assert p.explanations_verified_pct == 0 and p.no_recommendation == 0


def test_path_counts_plus_no_recommendation_equal_the_customers():
    rs = [result("a", "buy_out", 5000, revenue=900), result("b", "buy_out", 6000, revenue=800),
          result("c", "keep_as_is", 7000, baseline=7000), result("d", None, None, retained=False)]
    p = summarize(rs)
    assert sum(r.customers for r in p.by_path) + p.no_recommendation == p.customers_total == 4
    assert {r.path: r.customers for r in p.by_path}["buy_out"] == 2 and p.no_recommendation == 1


def test_revenue_is_the_sum_of_each_recommended_paths_revenue_by_path_and_in_total():
    rs = [result("a", "buy_out", 5000, revenue=900), result("b", "buy_out", 6000, revenue=800),
          result("c", "refinance", 7000, revenue=300)]
    p = summarize(rs)
    by = {r.path: r.revenue for r in p.by_path}
    assert by["buy_out"] == 1700 and by["refinance"] == 300 and by["walk_away"] == 0
    assert p.revenue_total == sum(by.values()) == 2000


def test_walking_away_is_not_retained_and_earns_nothing_even_if_a_revenue_figure_is_passed():
    p = summarize([
        result("a", "walk_away", 5000, retained=False, revenue=999),
        result("b", "buy_out", 5000, revenue=100),
    ])
    assert (p.retained_count, p.retained_pct, p.revenue_total) == (1, 50, 100)
    row = {r.path: r for r in p.by_path}["walk_away"]
    assert (row.stays_with_toyota, row.stays_label, row.revenue) == (False, "No", 0)


def test_the_stays_with_toyota_labels():
    labels = {r.path: r.stays_label for r in summarize([]).by_path}
    assert labels["buy_out"] == "Yes (Toyota loan)" and labels["walk_away"] == "No"
    stay = ("keep_as_is", "return_lease_new", "trade_in_early", "refinance", "extra_principal")
    assert all(labels[x] == "Yes" for x in stay)


def test_savings_are_keep_as_is_minus_the_recommended_cost_and_zero_when_keep_wins():
    rs = [result("a", "buy_out", 5000, baseline=9000), result("b", "keep_as_is", 7000, baseline=7000)]
    assert summarize(rs).avg_savings == 2000  # (4,000 + 0) / 2


def test_a_customer_with_nothing_affordable_is_left_out_of_the_savings_average_and_not_retained():
    rs = [result("a", "buy_out", 5000, baseline=9000, revenue=10), result("b", None, None, retained=False, baseline=1)]
    p = summarize(rs)
    assert p.avg_savings == 4000 and p.retained_count == 1 and p.retained_pct == 50 and p.no_recommendation == 1


def test_percentages_round_half_up_to_a_whole_percent():
    assert pct(1, 8) == 13  # 12.5
    assert pct(1, 3) == 33 and pct(2, 3) == 67 and pct(0, 5) == 0 and pct(3, 0) == 0
    rs = [result(str(i), "buy_out", 5000, verified=i < 1) for i in range(8)]
    assert summarize(rs).explanations_verified_pct == 13


def test_the_real_customers_reconcile_with_their_individual_results():
    rows = real_results()
    rs = [
        CustomerResult(cid, chosen.path if chosen else None, chosen.five_year_cost if chosen else None,
                       by["keep_as_is"].five_year_cost, bool(chosen and chosen.retained),
                       chosen.revenue if chosen else D(0), True)
        for cid, ev, by, chosen in rows
    ]
    p = summarize(rs)
    assert p.customers_total == 12
    assert sum(r.customers for r in p.by_path) + p.no_recommendation == 12
    assert p.no_recommendation == sum(1 for *_, chosen in rows if chosen is None)
    assert p.revenue_total == sum((chosen.revenue for *_, chosen in rows if chosen and chosen.retained), D(0))
    assert p.retained_count == sum(1 for *_, chosen in rows if chosen and chosen.retained)
    for row in p.by_path:
        assert row.customers == sum(1 for *_, chosen in rows if chosen and chosen.path == row.path)
    saved = [by["keep_as_is"].five_year_cost - chosen.five_year_cost for _, _, by, chosen in rows if chosen]
    assert p.avg_savings == (sum(saved, D(0)) / len(saved)).quantize(D(1), "ROUND_HALF_UP")
    assert all(s >= 0 for s in saved), "the recommended path is never costlier than keeping the current plan"
