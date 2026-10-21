"""Платежи по кредитам и задолженность по месяцам — для графика оборотов.

КИ отдаёт только текущий остаток и график платежей на год вперёд, поэтому прошлое
восстанавливаем оценкой: регулярный платёж с месяца после выдачи по текущий, долг убывает
линейно от лимита при выдаче до текущего остатка. Будущее — по графику платежей,
долг линейно гасится к дате погашения. Возобновляемые договоры без графика
(овердрафт, кредитная линия) держат текущий остаток весь срок.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.credit.forecast import add_months


@dataclass(frozen=True)
class Obligation:
    report_date: date  # на эту дату КИ дала остаток
    outstanding: Decimal
    opened: date | None = None
    maturity: date | None = None
    limit: Decimal | None = None
    schedule: list[tuple[date, Decimal]] = field(default_factory=list)


@dataclass(frozen=True)
class CreditMonth:
    month: date
    payments: Decimal  # плановые платежи за месяц
    debt: Decimal  # задолженность на конец месяца


def _month_end(month: date) -> date:
    return add_months(month, 1) - timedelta(days=1)


def _between(start: date, a: Decimal, end: date, b: Decimal, at: date) -> Decimal:
    """Линейно от a (на start) к b (на end)."""
    span = (end - start).days
    if span <= 0:
        return b
    share = Decimal((at - start).days) / Decimal(span)
    return a + (b - a) * share


def _payment(o: Obligation, month: date) -> Decimal:
    if month > o.report_date.replace(day=1):
        return sum(
            (amount for due, amount in o.schedule if due.replace(day=1) == month),
            Decimal(0),
        )
    # Прошлое и текущий месяц (часть его платежей уже списана и в графике их нет)
    if not o.schedule or o.opened is None or month <= o.opened.replace(day=1):
        return Decimal(0)
    if o.maturity is not None and month > o.maturity:
        return Decimal(0)
    return o.schedule[0][1]  # регулярный платёж, как в ближайшем по графику


def _debt(o: Obligation, month: date) -> Decimal:
    end = _month_end(month)
    if o.opened is not None and end < o.opened:
        return Decimal(0)
    if not o.schedule:
        return o.outstanding
    if end <= o.report_date:
        if o.opened is None:
            return o.outstanding
        start = max(o.limit or Decimal(0), o.outstanding)
        return _between(o.opened, start, o.report_date, o.outstanding, end)
    if o.maturity is None:
        return o.outstanding
    if end >= o.maturity:
        return Decimal(0)
    return _between(o.report_date, o.outstanding, o.maturity, Decimal(0), end)


def credit_by_month(
    obligations: list[Obligation], months: list[date]
) -> list[CreditMonth]:
    """Сумма по всем договорам на каждый месяц (первое число месяца)."""
    return [
        CreditMonth(
            month=m,
            payments=sum((_payment(o, m) for o in obligations), Decimal(0)),
            debt=sum((_debt(o, m) for o in obligations), Decimal(0)),
        )
        for m in months
    ]
