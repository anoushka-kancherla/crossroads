"""Exact decimal money helpers (FR-033, constitution principle II)."""

from decimal import Decimal as D

import pytest

from crossroads.engine.money import amortize, balance_after, cents, fmt_money, payment, whole


def test_payment_matches_a_known_loan():
    assert payment(20000, 6, 60) == D("386.66")


def test_payment_with_zero_rate_is_even_split():
    assert payment(12000, 0, 12) == D("1000.00")


def test_payment_for_zero_principal_is_zero():
    assert payment(0, 6, 12) == D("0.00")


def test_payment_rejects_negative_principal_and_bad_term():
    with pytest.raises(ValueError):
        payment(-1, 6, 12)
    with pytest.raises(ValueError):
        payment(1000, 6, 0)


def test_cents_rounds_half_up():
    assert cents(D("2.005")) == D("2.01")
    assert cents(D("2.004")) == D("2.00")
    assert cents("19.999") == D("20.00")


def test_whole_rounds_half_up_at_the_boundary():
    assert whole(D("2.5")) == D("3")
    assert whole(D("100.49")) == D("100")
    assert whole(D("100.50")) == D("101")


def test_costs_within_a_dollar_compare_equal_after_rounding():
    assert whole(D("100.40")) == whole(D("100.20"))
    assert whole(D("100.50")) != whole(D("100.49"))


def test_fmt_money_whole_dollars_with_commas_and_sign():
    assert fmt_money(D("31200.4")) == "$31,200"
    assert fmt_money(0) == "$0"
    assert fmt_money(D("-1200")) == "-$1,200"


def test_amortize_retires_the_principal_exactly():
    rows = amortize(12400, D("7.9"), 30)
    assert len(rows) == 30
    assert sum(r[2] for r in rows) == D(12400)
    assert rows[-1][3] == 0


def test_amortize_empty_input():
    assert amortize(0, 6, 12) == []


def test_extra_payment_shortens_the_loan_and_saves_interest():
    plain = amortize(12400, D("7.9"), 30)
    extra = amortize(12400, D("7.9"), 30, extra=300)
    assert len(extra) < len(plain)
    assert sum(r[1] for r in extra) < sum(r[1] for r in plain)
    assert extra[-1][3] == 0


def test_balance_after():
    rows = amortize(12400, D("7.9"), 30)
    assert balance_after(12400, D("7.9"), 30, 0) == D(12400)
    assert balance_after(12400, D("7.9"), 30, 1) == rows[0][3]
    assert balance_after(12400, D("7.9"), 30, 30) == 0
    assert balance_after(12400, D("7.9"), 30, 99) == 0
