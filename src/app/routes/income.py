from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_session, get_current_user_id
from app.exceptions import NotFoundError
from app.services import income as income_service
from app.types import BalanceSummary, IncomeCreate, IncomeRead, IncomeSummary, IncomeUpdate

router = APIRouter(
    prefix="/income",
    tags=["income"],
)


@router.get("/", response_model=list[IncomeRead])
async def list_income_endpoint(
    year: int | None = None,
    month: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> list[IncomeRead]:
    if year is not None and month is not None:
        return await income_service.list_incomes_for_month(
            session, user_id, year, month, limit=limit, offset=offset
        )
    return await income_service.list_income(session, user_id, limit=limit, offset=offset)


@router.get("/summary", response_model=IncomeSummary)
async def income_summary_endpoint(
    year: int,
    month: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> IncomeSummary:
    return await income_service.get_month_total(session, user_id, year, month)


@router.get("/balance", response_model=BalanceSummary)
async def balance_endpoint(
    year: int,
    month: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> BalanceSummary:
    return await income_service.get_balance(session, user_id, year, month)


@router.post("/", response_model=IncomeRead, status_code=status.HTTP_201_CREATED)
async def create_income_endpoint(
    data: IncomeCreate,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> IncomeRead:
    return await income_service.create_income(
        session, user_id=user_id, name=data.name, amount=data.amount, currency=data.currency, date=data.date
    )


@router.get("/{income_id}", response_model=IncomeRead)
async def get_income_endpoint(
    income_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> IncomeRead:
    try:
        return await income_service.get_income(session, user_id=user_id, income_id=income_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Доход не найден")


@router.patch("/{income_id}", response_model=IncomeRead)
async def update_income_endpoint(
    income_id: int,
    data: IncomeUpdate,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> IncomeRead:
    try:
        return await income_service.update_income(
            session,
            user_id=user_id,
            income_id=income_id,
            name=data.name,
            amount=data.amount,
            currency=data.currency,
            date=data.date,
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Доход не найден")


@router.delete("/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_income_endpoint(
    income_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> None:
    try:
        await income_service.delete_income(session, user_id=user_id, income_id=income_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Доход не найден")
