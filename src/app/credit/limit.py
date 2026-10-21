"""Предварительный лимит по DSCR: новый платёж должен помещаться в доход с запасом."""

from decimal import ROUND_DOWN, Decimal

MIN_DSCR = Decimal("1.25")
LIMIT_STEP = Decimal(
    1000
)  # лимит округляем вниз до тысячи — не больше, чем позволяет DSCR


def _monthly_rate(annual_rate_pct: Decimal) -> Decimal:
    return annual_rate_pct / Decimal(1200)


def annuity_payment(
    principal: Decimal, annual_rate_pct: Decimal, months: int
) -> Decimal:
    """Ежемесячный аннуитетный платёж."""
    r = _monthly_rate(annual_rate_pct)
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


def principal_for_payment(
    payment: Decimal, annual_rate_pct: Decimal, months: int
) -> Decimal:
    """Сколько можно взять при данном ежемесячном платеже (приведённая стоимость аннуитета)."""
    r = _monthly_rate(annual_rate_pct)
    if r == 0:
        return payment * months
    return payment * (1 - (1 + r) ** -months) / r


def dscr(monthly_income: Decimal, monthly_payments: Decimal) -> Decimal | None:
    """Покрытие платежей доходом; None, если платежей нет."""
    if monthly_payments <= 0:
        return None
    return monthly_income / monthly_payments


def dscr_limit(
    monthly_income: Decimal,
    monthly_payments: Decimal,
    annual_rate_pct: Decimal,
    term_months: int,
    min_dscr: Decimal = MIN_DSCR,
) -> Decimal:
    """Максимальная сумма нового кредита: доход ≥ min_dscr × (текущие платежи + новый)."""
    free_payment = monthly_income / min_dscr - monthly_payments
    if free_payment <= 0:
        return Decimal(0)
    amount = principal_for_payment(free_payment, annual_rate_pct, term_months)
    return (amount / LIMIT_STEP).to_integral_value(rounding=ROUND_DOWN) * LIMIT_STEP
