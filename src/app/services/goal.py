from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app import currency as currency_service
from app.exceptions import NotFoundError
from app.repositories import goal as goal_repo

from decimal import Decimal

async def create_goal(
    session: AsyncSession, user_id: int, name: str, target_amount: Decimal, months: int, currency: str
):
    goal = await goal_repo.create_goal(
        session, user_id=user_id, name=name, target_amount=target_amount, months=months, currency=currency
    )
    await session.commit()
    return _build_goal_read(goal, saved=Decimal(0))


async def _get_saved_amount(session: AsyncSession, goal_id: int, target_currency: str) -> Decimal:
    rows = await goal_repo.get_saved_by_currency(session, goal_id)
    total = Decimal(0)
    for row in rows:
        total += await currency_service.convert(session, row.total, row.currency, target_currency)
    return total

def _build_goal_read(goal, saved: Decimal) -> dict:
    monthly_target = (goal.target_amount / goal.months).quantize(Decimal("0.01"))

    if goal.target_amount > 0:
        pct = min(round(saved / goal.target_amount * 100), 100)
    else:
        pct = 0

    now = datetime.now(UTC)
    elapsed_months = (now.year - goal.created_at.year) * 12 + (now.month - goal.created_at.month)
    elapsed_months = max(elapsed_months, 1)

    expected_by_now = min(monthly_target * elapsed_months, goal.target_amount)
    if saved >= goal.target_amount:
        status = "done"
        behind_by = Decimal(0)
    elif saved >= expected_by_now:
        status = "on_track"
        behind_by = Decimal(0)
    else:
        status = "behind"
        behind_by = expected_by_now - saved

    return {
        "id": goal.id,
        "user_id": goal.user_id,
        "name": goal.name,
        "target_amount": goal.target_amount,
        "months": goal.months,
        "created_at": goal.created_at,
        "saved": saved,
        "pct": pct,
        "monthly_target": monthly_target,
        "status": status,
        "behind_by": behind_by,
        "currency": goal.currency,
    }


async def get_goal(session: AsyncSession, goal_id: int, user_id: int):
    goal = await goal_repo.get_goal_by_id(session, id = goal_id, user_id = user_id)
    if goal is None:
        raise NotFoundError
    saved = await _get_saved_amount(session, goal_id, goal.currency)
    return _build_goal_read(goal, saved)

async def list_goals(session: AsyncSession, user_id: int):
    goals = await goal_repo.list_goals(session, user_id)
    result = []
    for goal in goals:
        saved = await _get_saved_amount(session, goal.id, goal.currency)
        result.append(_build_goal_read(goal, saved))
    return result


async def get_active_monthly_target(session: AsyncSession, user_id: int, base_currency: str) -> Decimal:
    goals = await list_goals(session, user_id)
    total = Decimal(0)
    for g in goals:
        if g["status"] != "done":
            total += await currency_service.convert(session, g["monthly_target"], g["currency"], base_currency)
    return total

async def delete_goal(session: AsyncSession, goal_id: int, user_id: int):
    goal = await goal_repo.get_goal_by_id(session, id=goal_id, user_id=user_id)

    if goal is None:
        raise NotFoundError

    await goal_repo.delete_goal(session, goal)
    await session.commit()

async def add_contribution(
    session: AsyncSession, goal_id: int, user_id: int, amount: Decimal, currency: str
):
    exist_goal = await goal_repo.get_goal_by_id(session, id = goal_id, user_id=user_id)
    if exist_goal is None:
        raise NotFoundError

    contrb = await goal_repo.create_contribution(session, goal_id=goal_id, amount=amount, currency=currency)
    await session.commit()
    return contrb

async def list_contributions(session: AsyncSession, goal_id: int, user_id: int):
    goal = await goal_repo.get_goal_by_id(session, id = goal_id, user_id=user_id)

    if goal is None:
        raise NotFoundError

    return await goal_repo.list_contributions(session, goal_id)

async def delete_contribution(session: AsyncSession, goal_id: int, contribution_id: int, user_id: int):
    goal = await goal_repo.get_goal_by_id(session, id = goal_id, user_id = user_id)
    if goal is None:
        raise NotFoundError

    contribution = await goal_repo.get_contribution_by_id(session, id = contribution_id, goal_id = goal_id)
    if contribution is None:
        raise NotFoundError

    await goal_repo.delete_contribution(session, contribution)
    await session.commit()