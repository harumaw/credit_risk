from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_session, get_current_user_id
from app.exceptions import NotFoundError
from app.services import goal as goal_service
from app.types import GoalCreate, GoalRead, GoalContributionCreate, GoalContributionRead

router = APIRouter(
    prefix = "/goals",
    tags=["goals"]
)

@router.get("/", response_model=list[GoalRead])
async def list_goals_endpoint(
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
):
    return await goal_service.list_goals(session, user_id=user_id)


@router.post("/", response_model = GoalRead, status_code = status.HTTP_201_CREATED)
async def create_goal_endpoint(
    data: GoalCreate,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
):
    return await goal_service.create_goal(
        session, user_id, name=data.name, target_amount=data.target_amount, months=data.months,
        currency=data.currency,
    )

@router.get("/{goal_id}", response_model = GoalRead)
async def get_goal_endpoint(
    goal_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
):
    try:
        return await goal_service.get_goal(session, goal_id = goal_id, user_id = user_id)
    except NotFoundError:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Goal not found")

@router.delete("/{goal_id}", status_code = status.HTTP_204_NO_CONTENT)
async def delete_goal_endpoint(
    goal_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
):
    try:
        await goal_service.delete_goal(session, goal_id, user_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена")

@router.post("/{goal_id}/contributions", response_model = GoalContributionRead, status_code = status.HTTP_201_CREATED)
async def add_contribution_endpoint(
    goal_id: int,
    data: GoalContributionCreate,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
):
    try:
        return await goal_service.add_contribution(
            session, goal_id, user_id, amount=data.amount, currency=data.currency
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена")

@router.get("/{goal_id}/contributions", response_model=list[GoalContributionRead])
async def list_contributions_endpoint(
    goal_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> list[GoalContributionRead]:
    try:
        return await goal_service.list_contributions(session, goal_id, user_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена")


@router.delete("/{goal_id}/contributions/{contribution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contribution_endpoint(
    goal_id: int,
    contribution_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> None:
    try:
        await goal_service.delete_contribution(session, goal_id, contribution_id, user_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена")