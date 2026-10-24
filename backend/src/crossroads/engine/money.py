"""Exact decimal money helpers (constitution, principle II). No floats anywhere."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal(0)
_CENT = Decimal("0.01")
_ONE = Decimal(1)


def D(x: Decimal | int | str) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def cents(x: Decimal | int | str) -> Decimal:
    return D(x).quantize(_CENT, ROUND_HALF_UP)


def whole(x: Decimal | int | str) -> Decimal:
    """Round to whole dollars, half up. Costs are compared in this form (FR-033)."""
    return D(x).quantize(_ONE, ROUND_HALF_UP)


def fmt_money(x: Decimal | int | str) -> str:
    v = int(whole(x))
    return f"-${-v:,}" if v < 0 else f"${v:,}"


def payment(principal: Decimal | int | str, apr_pct: Decimal | int | str, months: int) -> Decimal:
    """Level monthly payment that retires `principal` in `months` at `apr_pct` percent APR."""
    p = D(principal)
    if p < 0:
        raise ValueError("principal must not be negative")
    if months <= 0:
        raise ValueError("months must be positive")
    if p == 0:
        return cents(0)
    r = D(apr_pct) / Decimal(1200)
    if r == 0:
        return cents(p / months)
    f = (_ONE + r) ** months
    return cents(p * r * f / (f - _ONE))


def amortize(
    principal: Decimal | int | str,
    apr_pct: Decimal | int | str,
    months: int,
    extra: Decimal | int | str = 0,
) -> list[tuple[Decimal, Decimal, Decimal, Decimal]]:
    """Month-by-month schedule as (payment, interest, principal_paid, balance_after).

    `extra` is added to every payment, so the loan can end before `months`. The last scheduled
    payment clears whatever rounding left behind.
    """
    bal = D(principal)
    r = D(apr_pct) / Decimal(1200)
    pay = payment(bal, apr_pct, months) + D(extra)
    rows: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
    for i in range(months):
        if bal <= 0:
            break
        interest = cents(bal * r)
        due = bal + interest if (i == months - 1 or pay >= bal + interest) else pay
        princ = due - interest
        bal = bal - princ
        rows.append((due, interest, princ, bal))
    return rows


def balance_after(
    principal: Decimal | int | str, apr_pct: Decimal | int | str, months: int, k: int
) -> Decimal:
    rows = amortize(principal, apr_pct, months)
    if k <= 0:
        return D(principal)
    return rows[k - 1][3] if k <= len(rows) else ZERO
