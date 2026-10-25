"""Наши собственные кредиты компании — чистые функции.

БКИ узнаёт о кредите, который выдали мы, не сразу (а симулятор не узнаёт вовсе), поэтому
лимит считаем с учётом своих обязательств: выданных кредитов (`loans`) и принятых, но ещё
не выданных предложений. Без этого можно взять максимум, а потом ещё раз столько же.
"""

import calendar
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.credit.features import months_between
from app.credit.limit import MIN_DSCR, annuity_payment


@dataclass(frozen=True)
class OwnCredit:
    amount: Decimal
    rate: Decimal  # годовая ставка, %
    term_months: int
    issued_at: date | None  # None — предложение принято, деньги ещё не выданы
    application_id: uuid.UUID | None = None
    product_type: str | None = None

    @property
    def monthly_payment(self) -> Decimal:
        return annuity_payment(self.amount, self.rate, self.term_months).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )

    def outstanding(self, today: date) -> Decimal:
        """Остаток долга по графику аннуитета после прошедших платежей."""
        if self.issued_at is None:
            return self.amount
        paid = min(max(months_between(self.issued_at, today), 0), self.term_months)
        if paid >= self.term_months:
            return Decimal(0)
        r = self.rate / Decimal(1200)
        if r == 0:
            return self.amount * (self.term_months - paid) / self.term_months
        p = annuity_payment(self.amount, self.rate, self.term_months)
        rest = self.amount * (1 + r) ** paid - p * ((1 + r) ** paid - 1) / r
        return max(rest, Decimal(0)).quantize(Decimal(1), rounding=ROUND_HALF_UP)

    def next_payment_date(self, today: date) -> date | None:
        """Ближайший платёж по графику: через месяц после выдачи и далее ежемесячно."""
        if self.issued_at is None:
            return None
        paid = max(months_between(self.issued_at, today), 0)
        if paid >= self.term_months:
            return None
        return maturity_date(self.issued_at, paid + 1)


def own_payments(credits: list[OwnCredit]) -> Decimal:
    return sum((c.monthly_payment for c in credits), Decimal(0))


def fits_dscr(income: Decimal | None, payments: Decimal, new_payment: Decimal) -> bool:
    """Новый платёж помещается в доход с запасом MIN_DSCR вместе с текущими платежами."""
    if income is None:
        return False
    return income >= MIN_DSCR * (payments + new_payment)


def maturity_date(issued_at: date, term_months: int) -> date:
    """Дата погашения: тот же день через срок (или последний день короткого месяца)."""
    year, month = divmod(issued_at.month - 1 + term_months, 12)
    year += issued_at.year
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(issued_at.day, last))
