"""Pure fairness statistics: bands, the profitability rank, band summaries, the verdict and its sentences."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from crossroads.engine import fairness as f

EDGES = (D(4500), D(6500))


def res(rec, others=(), income=5000, kind="loan", path="buy_out"):
    """A result whose recommended option earns `rec`; `others` are the other affordable options' revenues."""
    return f.PopulationResult(D(income), kind, path, D(rec), (D(rec), *map(D, others)))


NONE = f.PopulationResult(D(3000), "loan", None, D(0), ())


# --- bands --------------------------------------------------------------------------------------------


def test_band_labels_for_the_defaults():
    assert [b.label for b in f.bands_from(EDGES)] == [
        "Under $4,500 a month", "$4,500 to $6,499 a month", "$6,500 or more a month",
    ]


@pytest.mark.parametrize(
    "income,idx", [("4499.99", 0), ("4500", 1), ("6499.99", 1), ("6500", 2), ("0", 0), ("99999", 2)]
)
def test_a_boundary_income_joins_the_higher_band(income, idx):
    assert f.band_index(D(income), EDGES) == idx


# --- the rank -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rec,others,rank",
    [
        (100, (200, 300), "0"),  # lowest of three
        (300, (100, 200), "1"),  # highest of three
        (200, (100, 300), "0.5"),  # middle of three
        (200, (100,), "1"),  # two options, the higher
        (100, (200,), "0"),
        (100, (100, 100), "0.5"),  # all tied
        (0, (100, 200), "0"),  # walk-away at zero
        (200, (200, 100), "0.75"),  # tie with one, above one: (1 + 0.5) / 2
    ],
)
def test_profitability_rank(rec, others, rank):
    assert f.profitability_rank(res(rec, others)) == D(rank)


def test_one_option_or_none_has_no_rank():
    assert f.profitability_rank(res(100)) is None
    assert f.profitability_rank(NONE) is None
    assert not res(100).has_choice and res(100).has_recommendation
    assert not NONE.has_recommendation
    assert res(100, (50,)).has_choice


def test_most_profitable_counts_ties_and_given_up_is_never_negative():
    assert f.is_most_profitable(res(300, (100, 300)))
    assert not f.is_most_profitable(res(200, (300,)))
    assert f.given_up(res(300, (100,))) == 0
    assert f.given_up(res(100, (350,))) == 250


# --- band summaries -----------------------------------------------------------------------------------


LOW = f.bands_from(EDGES)[0]


def test_a_basic_summary():
    rs = [res(100, (200,)), res(200, (100,), path="refinance"), res(50), NONE]
    s = f.summarize_band(LOW, rs)
    assert (s.customers, s.with_recommendation, s.no_affordable) == (4, 3, 1)
    assert s.path_counts == (("buy_out", 2), ("refinance", 1))
    assert sum(c for _, c in s.path_counts) == s.with_recommendation
    assert (s.with_choice, s.single_option, s.avg_rank_n) == (2, 1, 2)
    assert s.with_choice + s.single_option == s.with_recommendation
    assert s.avg_rank_pct == D("50.0")  # ranks 0 and 1


def test_an_empty_band_and_a_band_without_choice_give_none_never_zero():
    e = f.summarize_band(LOW, [])
    assert e.customers == 0 and e.avg_rank_pct is None and e.avg_revenue is None
    assert e.avg_affordable_options is None and e.no_affordable_share_pct is None
    s = f.summarize_band(LOW, [res(100), NONE])
    assert s.avg_rank_pct is None and s.avg_given_up is None and s.with_choice == 0


def test_the_average_rank_rounds_half_up_to_one_decimal():
    # ranks 1, 0, 0, 0, 0, 0, 0, 0 over 8 customers: 12.5 exactly, which rounds up
    rs = [res(200, (100,))] + [res(100, (200,)) for _ in range(7)]
    assert f.summarize_band(LOW, rs).avg_rank_pct == D("12.5")
    # 1/3 -> 33.3
    rs = [res(200, (100,)), res(100, (200,)), res(100, (200,))]
    assert f.summarize_band(LOW, rs).avg_rank_pct == D("33.3")


def test_evidence_fields():
    rs = [
        res(300, (100,)),  # most profitable, gave up 0
        res(100, (350,)),  # gave up 250
        res(0, (400, 200), path="walk_away"),  # walk-away counts as zero revenue; gave up 400
        res(80),  # single option: left out of rank and most-profitable, kept in revenue
        NONE,  # no affordable option: in no average except the share and the option count
    ]
    s = f.summarize_band(LOW, rs)
    assert s.most_profitable_count == 1
    assert s.avg_given_up == D("216.67")  # (0 + 250 + 400) / 3
    assert s.avg_revenue == D("120.00") and s.avg_revenue_n == 4  # (300 + 100 + 0 + 80) / 4
    assert s.avg_affordable_options == D("1.6")  # (2 + 2 + 3 + 1 + 0) / 5 counts the zero
    assert s.no_affordable_share_pct == D("20.0")
    assert s.single_option == 1 and s.with_choice == 3


# --- the verdict --------------------------------------------------------------------------------------


def est(gap, lo, hi, n_low=157, n_high=165):
    return f.GapEstimate("all", True, n_low, n_high, D(gap), D(lo), D(hi))


def test_enough_needs_the_minimum_in_both_bands():
    assert not f.is_enough(29, 100, 30) and not f.is_enough(100, 29, 30)
    assert f.is_enough(30, 30, 30)


def test_make_estimate_converts_rank_units_to_points_once():
    g = f.make_estimate("all", 50, 60, 30, D("0.0149"), (D("-0.062"), D("0.09")))
    assert (g.gap_points, g.ci_low, g.ci_high) == (D("1.5"), D("-6.2"), D("9.0"))
    short = f.make_estimate("loan", 29, 60, 30, D("0.1"), (D("0"), D("0.2")))
    assert not short.enough and short.gap_points is None and short.ci_low is None


def test_no_evidence_sentence_and_notes():
    v = f.decide(est("1.4", "-6.2", "9.0"), D(15), 30)
    assert v.outcome == "no_evidence" and v.interval_note is None
    assert v.sentence == (
        "No evidence that lower-income customers are steered toward paths that earn Toyota more interest: "
        "the lowest-income band's recommendations rank 1.4 points higher than the highest-income band's "
        "(95% interval -6.2 to 9.0, from 157 and 165 customers with a real choice)."
    )
    assert (v.gap_points, v.ci_low, v.ci_high, v.lowest_n, v.highest_n) == (D("1.4"), D("-6.2"), D("9.0"), 157, 165)
    wide = f.decide(est("4.0", "-8.0", "15.1"), D(15), 30)
    assert wide.outcome == "no_evidence"
    assert wide.interval_note == "The data cannot rule out a gap beyond the 15-point threshold."
    assert f.decide(est("4.0", "-8.0", "15.0"), D(15), 30).interval_note is None  # 15.0 is not above 15


def test_a_gap_the_other_way_says_lower_and_a_zero_gap_says_the_same():
    lower = f.decide(est("-3.2", "-9", "2"), D(15), 30)
    assert "rank 3.2 points lower than the highest-income band's" in lower.sentence
    assert "rank the same as the highest-income band's" in f.decide(est("0.0", "-4", "4"), D(15), 30).sentence


def test_the_threshold_test_uses_the_displayed_gap():
    assert f.decide(est("15.0", "10", "20"), D(15), 30).outcome == "no_evidence"  # 15.04 displays as 15.0
    assert f.decide(est("15.1", "10", "20"), D(15), 30).outcome == "possible_steering"  # 15.05 displays as 15.1


def test_possible_steering_sentence_and_notes():
    v = f.decide(est("22.0", "12.4", "31.0"), D(15), 30)
    assert v.outcome == "possible_steering"
    assert v.sentence == (
        "Possible steering of lower-income customers toward paths that earn Toyota more interest, to be reviewed: "
        "the lowest-income band's recommendations rank 22.0 points higher than the highest-income band's, "
        "more than the 15-point threshold (95% interval 12.4 to 31.0, from 157 and 165 customers with a real choice)."
    )
    assert v.interval_note == "The data cannot confirm the gap is beyond the 15-point threshold."
    assert f.decide(est("22.0", "15.0", "31.0"), D(15), 30).interval_note == v.interval_note  # at the threshold
    whole = f.decide(est("22.0", "15.1", "31.0"), D(15), 30)
    assert whole.interval_note == "The whole interval is beyond the 15-point threshold."


def test_an_unfavourable_verdict_is_not_softened():
    v = f.decide(est("22.0", "15.1", "31.0"), D(15), 30)
    assert v.outcome == "possible_steering" and v.sentence.startswith("Possible steering")
    assert v.gap_points is not None and v.ci_low is not None and v.ci_high is not None


def test_not_enough_sentences():
    short = f.GapEstimate("all", False, 29, 165)
    v = f.decide(short, D(15), 30, lowest_customers=160, highest_customers=165)
    assert v.outcome == "not_enough" and v.gap_points is None and v.ci_low is None and v.interval_note is None
    assert v.sentence == (
        "Not enough customers to tell: the comparison needs at least 30 customers with a real choice in both "
        "the lowest-income band (29) and the highest-income band (165)."
    )
    one = f.decide(f.GapEstimate("all", False, 0, 500), D(15), 30, lowest_customers=0, highest_customers=500)
    assert one.sentence == (
        "Not enough customers to tell: there is nothing to compare, because every customer falls in one income band."
    )


def test_a_custom_threshold_is_quoted():
    v = f.decide(est("1.0", "-2", "13"), D("12.5"), 30)
    assert v.interval_note == "The data cannot rule out a gap beyond the 12.5-point threshold."


def test_the_gap_between_two_samples():
    assert f.gap_between([D(1), D(0)], [D("0.25")]) == D("0.25")
