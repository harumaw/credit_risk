from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Income


async def get_income_by_id(session: AsyncSession, id: int, user_id: int) -> Income | None:
    stmt = select(Income).where(Income.id == id, Income.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_incomes(
    session: AsyncSession, user_id: int, limit: int = 50, offset: int = 0
) -> list[Income]:
    stmt = (
        select(Income)
        .where(Income.user_id == user_id)
        .order_by(Income.id)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def list_incomes_by_period(
    session: AsyncSession,
    user_id: int,
    date_from: datetime,
    date_to: datetime,
    limit: int = 50,
    offset: int = 0,
) -> list[Income]:
    stmt = (
        select(Income)
        .where(
            Income.user_id == user_id,
            Income.created_at >= date_from,
            Income.created_at < date_to,
        )
        .order_by(Income.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_totals_by_currency(
    session: AsyncSession, user_id: int, date_from: datetime, date_to: datetime
):
    stmt = (
        select(
            Income.currency,
            func.sum(Income.amount).label("total"),
            func.count(Income.id).label("count"),
        )
        .where(
            Income.user_id == user_id,
            Income.created_at >= date_from,
            Income.created_at < date_to,
        )
        .group_by(Income.currency)
    )
    result = await session.execute(stmt)
    return result.all()


async def create_income(
    session: AsyncSession, user_id: int, name: str, amount: Decimal, currency: str, created_at: datetime,
) -> Income:
    income = Income(user_id=user_id, name=name, amount=amount, currency=currency, created_at=created_at)
    session.add(income)
    await session.flush()
    await session.refresh(income)
    return income


async def update_income(
    session: AsyncSession, income: Income, *,
    name: str | None = None, amount: Decimal | None = None, currency: str | None = None,
    created_at: datetime | None = None,
) -> Income:
    if name is not None:
        income.name = name
    if amount is not None:
        income.amount = amount
    if currency is not None:
        income.currency = currency
    if created_at is not None:
        income.created_at = created_at
    await session.flush()
    await session.refresh(income)
    return income


async def delete_income(session: AsyncSession, income: Income) -> None:
    await session.delete(income)
    await session.flush()
