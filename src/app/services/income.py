from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app import currency as currency_service
from app.exceptions import NotFoundError
from app.models import Income
from app.repositories import income as income_repo
from app.repositories import user as user_repo
from app.services.expense import _month_bounds, get_month_summary
from app.services.goal import get_active_monthly_target


async def list_incomes_for_month(
    session: AsyncSession, user_id: int, year: int, month: int, limit: int = 50, offset: int = 0
) -> list[Income]:
    date_from, date_to = _month_bounds(year, month)
    return await income_repo.list_incomes_by_period(
        session, user_id, date_from, date_to, limit=limit, offset=offset
    )


async def get_month_total(session: AsyncSession, user_id: int, year: int, month: int) -> dict:
    date_from, date_to = _month_bounds(year, month)
    rows = await income_repo.get_totals_by_currency(session, user_id, date_from, date_to)

    user = await user_repo.get_user_by_id(session, user_id)
    base_currency = user.base_currency

    total = Decimal(0)
    count = 0
    for r in rows:
        total += await currency_service.convert(session, r.total, r.currency, base_currency)
        count += r.count

    return {
        "total": total,
        "count": count,
        "avg": round(total / count, 2) if count else Decimal(0),
        "currency": base_currency,
    }


async def get_balance(session: AsyncSession, user_id: int, year: int, month: int) -> dict:
    user = await user_repo.get_user_by_id(session, user_id)
    base_currency = user.base_currency

    income_totals = await get_month_total(session, user_id, year, month)
    expense_summary = await get_month_summary(session, user_id, year, month)
    goals_monthly = await get_active_monthly_target(session, user_id, base_currency)

    balance = income_totals["total"] - expense_summary["total"] - goals_monthly

    return {
        "income": income_totals["total"],
        "expenses": expense_summary["total"],
        "goals_monthly": goals_monthly,
        "balance": balance,
        "currency": base_currency,
    }


async def create_income(
    session: AsyncSession, user_id: int, name: str, amount: Decimal, currency: str,
    date: datetime | None = None,
) -> Income:
    created_at = date if date is not None else datetime.now(UTC)
    income = await income_repo.create_income(
        session, user_id=user_id, name=name, amount=amount, currency=currency, created_at=created_at
    )
    await session.commit()
    return income


async def get_income(session: AsyncSession, user_id: int, income_id: int) -> Income:
    income = await income_repo.get_income_by_id(session, income_id, user_id)
    if income is None:
        raise NotFoundError
    return income


async def list_income(session: AsyncSession, user_id: int, limit: int = 50, offset: int = 0):
    return await income_repo.list_incomes(session, user_id, limit=limit, offset=offset)


async def delete_income(session: AsyncSession, user_id: int, income_id: int) -> None:
    income = await income_repo.get_income_by_id(session, income_id, user_id)
    if income is None:
        raise NotFoundError

    await income_repo.delete_income(session, income)
    await session.commit()


async def update_income(
    session: AsyncSession, user_id: int, income_id: int, *,
    name: str | None = None, amount: Decimal | None = None, currency: str | None = None,
    date: datetime | None = None,
) -> Income:
    income = await income_repo.get_income_by_id(session, income_id, user_id)
    if income is None:
        raise NotFoundError

    income = await income_repo.update_income(
        session, income, name=name, amount=amount, currency=currency, created_at=date
    )
    await session.commit()
    return income
