from calendar import monthrange
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app import currency as currency_service
from app.exceptions import AlreadyExistsError, NotFoundError
from app.models import Expense
from app.repositories import expense as expense_repo
from app.repositories import category as category_repo
from app.repositories import user as user_repo

from decimal import Decimal


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    date_from = datetime(year, month, 1, tzinfo=UTC)
    last_day = monthrange(year, month)[1]
    date_to = date_from + timedelta(days=last_day)
    return date_from, date_to


async def list_expenses_for_month(
    session: AsyncSession, user_id: int, year: int, month: int, limit: int = 50, offset: int = 0
) -> list[Expense]:
    date_from, date_to = _month_bounds(year, month)
    return await expense_repo.list_expenses_by_period(
        session, user_id, date_from, date_to, limit=limit, offset=offset
    )


async def get_month_summary(session: AsyncSession, user_id: int, year: int, month: int) -> dict:
    date_from, date_to = _month_bounds(year, month)
    rows = await expense_repo.get_category_totals(session, user_id, date_from, date_to)

    user = await user_repo.get_user_by_id(session, user_id)
    base_currency = user.base_currency

    category_sums: dict[int, Decimal] = {}
    category_counts: dict[int, int] = {}
    total = Decimal(0)
    count = 0

    for r in rows:
        converted = await currency_service.convert(session, r.total, r.currency, base_currency)
        category_sums[r.categories_id] = category_sums.get(r.categories_id, Decimal(0)) + converted
        category_counts[r.categories_id] = category_counts.get(r.categories_id, 0) + r.count
        total += converted
        count += r.count

    breakdown = []
    for categories_id, sum_ in category_sums.items():
        category = await category_repo.get_category_by_id(session, categories_id, user_id)
        breakdown.append({
            "categories_id": categories_id,
            "name": category.name,
            "sum": sum_,
            "count": category_counts[categories_id],
            "pct": round(sum_ / total * 100) if total else 0,
        })

    return {
        "total": total,
        "count": count,
        "avg": round(total / count, 2) if count else Decimal(0),
        "breakdown": breakdown,
        "currency": base_currency,
    }

async def get_trends(session: AsyncSession, user_id: int, months: int = 6) -> dict:
    today = datetime.now(UTC)
    year, month = today.year, today.month

    month_list = []
    for _ in range(months):
        month_list.append((year, month))
        month -= 1
        if month < 1:
            month = 12
            year -= 1
    month_list.reverse()

    points = []
    category_totals: dict[int, dict] = {}

    for y, m in month_list:
        summary = await get_month_summary(session, user_id, y, m)
        points.append({"year": y, "month": m, "total": summary["total"]})
        for b in summary["breakdown"]:
            entry = category_totals.setdefault(
                b["categories_id"], {"categories_id": b["categories_id"], "name": b["name"], "sum": Decimal(0)}
            )
            entry["sum"] += b["sum"]

    top_categories = sorted(category_totals.values(), key=lambda x: x["sum"], reverse=True)[:5]

    user = await user_repo.get_user_by_id(session, user_id)

    return {
        "points": points,
        "top_categories": top_categories,
        "currency": user.base_currency,
    }


async def create_expense(
    session: AsyncSession, user_id: int, categories_id: int, name: str, amount: Decimal, currency: str,
    date: datetime | None = None,
):
    category = await category_repo.get_category_by_id(session, categories_id, user_id)
    if category is None:
        raise NotFoundError

    created_at = date if date is not None else datetime.now(UTC)

    expense = await expense_repo.create_expense(
        session, user_id=user_id, categories_id=categories_id, name=name, amount=amount, currency=currency,
        created_at=created_at,
    )
    await session.commit()
    return expense

async def get_expense(session: AsyncSession, user_id: int, expense_id: int):
    expense = await expense_repo.get_expense_by_id(session, expense_id, user_id)
    if expense is None:
        raise NotFoundError
    return expense

async def list_expense(session: AsyncSession, user_id: int, limit: int = 50, offset: int = 0):
    return await expense_repo.list_expenses(session, user_id, limit=limit, offset=offset)

async def delete_expense(session: AsyncSession, user_id: int, expense_id: int):
    expense_check = await expense_repo.get_expense_by_id(session, expense_id, user_id)
    if expense_check is None:
        raise NotFoundError

    await expense_repo.delete_expense(session, expense_check)
    await session.commit()

async def update_expense(session: AsyncSession,user_id: int, expense_id: int, *,
                        categories_id: int | None = None, name: str | None = None, amount: Decimal | None = None,
                        currency: str | None = None, date: datetime | None = None,
) -> Expense:
    expense = await expense_repo.get_expense_by_id(session, expense_id, user_id)
    if expense is None:
        raise NotFoundError

    if categories_id is not None:
        category = await category_repo.get_category_by_id(session, categories_id, user_id)
        if category is None:
            raise NotFoundError

    expense = await expense_repo.update_expense(
        session, expense, categories_id=categories_id, name=name, amount=amount, currency=currency,
        created_at=date,
    )
    await session.commit()
    return expense
