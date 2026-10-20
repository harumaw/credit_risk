from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Goal, GoalContribution


async def get_goal_by_id(session: AsyncSession, id: int, user_id: int) -> Goal | None:
    stmt = select(Goal).where(Goal.id == id, Goal.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_goals(session: AsyncSession, user_id: int) -> list[Goal]:
    stmt = select(Goal).where(Goal.user_id == user_id).order_by(Goal.id)
    result = await session.execute(stmt)
    return result.scalars().all()


async def create_goal(
    session: AsyncSession, user_id: int, name: str, target_amount: Decimal, months: int, currency: str
) -> Goal:
    goal = Goal(user_id=user_id, name=name, target_amount=target_amount, months=months, currency=currency)
    session.add(goal)
    await session.flush()
    await session.refresh(goal)
    return goal


async def delete_goal(session: AsyncSession, goal: Goal) -> None:
    await session.delete(goal)
    await session.flush()


async def get_saved_by_currency(session: AsyncSession, goal_id: int):
    stmt = (
        select(GoalContribution.currency, func.sum(GoalContribution.amount).label("total"))
        .where(GoalContribution.goal_id == goal_id)
        .group_by(GoalContribution.currency)
    )
    result = await session.execute(stmt)
    return result.all()


async def create_contribution(
    session: AsyncSession, goal_id: int, amount: Decimal, currency: str
) -> GoalContribution:
    contribution = GoalContribution(goal_id=goal_id, amount=amount, currency=currency)
    session.add(contribution)
    await session.flush()
    await session.refresh(contribution)
    return contribution


async def list_contributions(session: AsyncSession, goal_id: int) -> list[GoalContribution]:
    stmt = (
        select(GoalContribution)
        .where(GoalContribution.goal_id == goal_id)
        .order_by(GoalContribution.created_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_contribution_by_id(
    session: AsyncSession, id: int, goal_id: int
) -> GoalContribution | None:
    stmt = select(GoalContribution).where(
        GoalContribution.id == id, GoalContribution.goal_id == goal_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_contribution(session: AsyncSession, contribution: GoalContribution) -> None:
    await session.delete(contribution)
    await session.flush()
