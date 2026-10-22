from datetime import date
from decimal import Decimal

from app.credit.debt import Obligation, credit_by_month

TODAY = date(2026, 10, 21)

LOAN = Obligation(
    report_date=TODAY,
    outstanding=Decimal(1_200_000),
    opened=date(2025, 10, 21),
    maturity=date(2027, 10, 21),
    limit=Decimal(2_400_000),
    schedule=[
        (date(2026, 10, 25), Decimal(100_000)),
        (date(2026, 11, 25), Decimal(100_000)),
    ],
)


def _by_month(obligations, *months):
    return {c.month: c for c in credit_by_month(obligations, list(months))}


def test_past_payments_are_regular_from_month_after_opening():
    c = _by_month([LOAN], date(2025, 10, 1), date(2025, 11, 1), date(2026, 9, 1))

    assert c[date(2025, 10, 1)].payments == 0  # месяц выдачи
    assert c[date(2025, 11, 1)].payments == 100_000
    assert c[date(2026, 9, 1)].payments == 100_000


def test_future_payments_follow_schedule():
    paid_this_month = Obligation(**{**LOAN.__dict__, "schedule": LOAN.schedule[1:]})
    c = _by_month(
        [paid_this_month], date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)
    )

    assert c[date(2026, 10, 1)].payments == 100_000  # уже списан, но в месяце учтён
    assert c[date(2026, 11, 1)].payments == 100_000
    assert c[date(2026, 12, 1)].payments == 0  # графика дальше нет


def test_debt_goes_from_limit_to_outstanding_and_then_to_zero():
    months = [
        date(2025, 9, 1),
        date(2026, 4, 1),
        date(2026, 9, 1),
        date(2027, 4, 1),
        date(2027, 10, 1),
    ]
    debt = [c.debt for c in credit_by_month([LOAN], months)]

    assert debt[0] == 0  # ещё не выдан
    assert Decimal(1_200_000) < debt[2] < debt[1] < Decimal(2_400_000)
    assert 0 < debt[3] < Decimal(1_200_000)
    assert debt[4] == 0  # погашен в срок


def test_revolving_without_schedule_keeps_outstanding():
    overdraft = Obligation(
        report_date=TODAY, outstanding=Decimal(300_000), opened=date(2026, 1, 10)
    )

    c = _by_month([overdraft], date(2025, 12, 1), date(2026, 5, 1), date(2026, 12, 1))

    assert c[date(2025, 12, 1)].debt == 0
    assert c[date(2026, 5, 1)].debt == c[date(2026, 12, 1)].debt == 300_000
    assert all(m.payments == 0 for m in c.values())


def test_sums_over_obligations():
    other = Obligation(report_date=TODAY, outstanding=Decimal(50_000))

    c = _by_month([LOAN, other], date(2026, 11, 1))[date(2026, 11, 1)]

    assert c.payments == 100_000
    assert c.debt > 50_000
