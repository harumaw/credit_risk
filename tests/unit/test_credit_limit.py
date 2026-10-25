from datetime import date
from decimal import Decimal

from app.credit.forecast import add_months, linear_forecast
from app.credit.limit import annuity_payment, dscr, dscr_limit


def test_dscr_limit_matches_case_example():
    # пример из постановки: доход 450 тыс, платежи 100 тыс, 24% — 12 мес ≈ 2,75 млн, 24 мес ≈ 4,92 млн
    income, payments, rate = Decimal(450_000), Decimal(100_000), Decimal(24)

    assert dscr_limit(income, payments, rate, 12) == Decimal(2_749_000)
    assert dscr_limit(income, payments, rate, 24) == Decimal(4_917_000)


def test_limit_never_breaks_dscr():
    income, payments, rate = Decimal(450_000), Decimal(100_000), Decimal(24)
    limit = dscr_limit(income, payments, rate, 12)

    new_payment = annuity_payment(limit, rate, 12)
    assert income / (payments + new_payment) >= Decimal("1.25")


def test_no_limit_when_payments_eat_income():
    assert dscr_limit(Decimal(100_000), Decimal(90_000), Decimal(24), 12) == 0


def test_dscr_without_payments_is_none():
    assert dscr(Decimal(450_000), Decimal(0)) is None
    assert dscr(Decimal(450_000), Decimal(100_000)) == Decimal("4.5")


def test_forecast_continues_trend():
    history = [Decimal(v) for v in range(100, 220, 10)]  # 12 мес, +10 в месяц

    points = linear_forecast(history, last_month=date(2026, 9, 1))

    assert [p.month for p in points] == [
        date(2026, 10, 1),
        date(2026, 11, 1),
        date(2026, 12, 1),
    ]
    assert [p.value for p in points] == [Decimal(220), Decimal(230), Decimal(240)]
    assert all(p.lower == p.value == p.upper for p in points)  # идеальная прямая


def test_forecast_never_negative():
    history = [Decimal(v) for v in (300, 200, 100, 0)]
    points = linear_forecast(history, last_month=date(2026, 9, 1))
    assert all(p.value >= 0 and p.lower >= 0 for p in points)


def test_add_months_crosses_year():
    assert add_months(date(2026, 11, 1), 3) == date(2027, 2, 1)
    assert add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
