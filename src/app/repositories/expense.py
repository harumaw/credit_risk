from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.models import Expense

async def get_expense_by_id(session: AsyncSession, id:int, user_id: int) -> Expense | None:
    stmt = select(Expense).where(Expense.id == id, Expense.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def list_expenses(
    session: AsyncSession, user_id: int, limit: int = 50, offset: int = 0
) -> list[Expense]:
    stmt = (
        select(Expense)
        .where(Expense.user_id == user_id)
        .order_by(Expense.id)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def list_expenses_by_period(
    session: AsyncSession,
    user_id: int,
    date_from: datetime,
    date_to: datetime,
    limit: int = 50,
    offset: int = 0,
) -> list[Expense]:
    stmt = (
        select(Expense)
        .where(
            Expense.user_id == user_id,
            Expense.created_at >= date_from,
            Expense.created_at < date_to,
        )
        .order_by(Expense.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_category_totals(
    session: AsyncSession, user_id: int, date_from: datetime, date_to: datetime
):
    stmt = (
        select(
            Expense.categories_id,
            Expense.currency,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .where(
            Expense.user_id == user_id,
            Expense.created_at >= date_from,
            Expense.created_at < date_to,
        )
        .group_by(Expense.categories_id, Expense.currency)
    )
    result = await session.execute(stmt)
    return result.all()


async def create_expense(
    session: AsyncSession, user_id: int, categories_id: int, name: str, amount: Decimal, currency: str,
    created_at: datetime,
) -> Expense:
    expense = Expense(
        user_id=user_id, categories_id=categories_id, name=name, amount=amount, currency=currency,
        created_at=created_at,
    )

    session.add(expense)
    await session.flush()
    await session.refresh(expense)
    return expense

async def update_expense(session: AsyncSession, expense: Expense, *,
                        categories_id: int | None = None, name: str | None = None, amount: Decimal | None = None,
                        currency: str | None = None, created_at: datetime | None = None) -> Expense:
    if categories_id is not None:
        expense.categories_id = categories_id
    if name is not None:
        expense.name = name
    if amount is not None:
        expense.amount = amount
    if currency is not None:
        expense.currency = currency
    if created_at is not None:
        expense.created_at = created_at
    await session.flush()
    await session.refresh(expense)
    return expense

async def delete_expense(session: AsyncSession, expense: Expense) -> None:
    await session.delete(expense)
    await session.flush()
