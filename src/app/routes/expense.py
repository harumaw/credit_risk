from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_session, get_current_user_id
from app.exceptions import NotFoundError
from app.services import expense as expense_service
from app.types import ExpenseCreate, ExpenseRead, ExpenseSummary, ExpenseTrends, ExpenseUpdate

router = APIRouter(
    prefix="/expenses",
    tags=["expenses"],
)


@router.get("/", response_model=list[ExpenseRead])
async def list_expenses_endpoint(
    year: int | None = None,
    month: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> list[ExpenseRead]:
    if year is not None and month is not None:
        return await expense_service.list_expenses_for_month(
            session, user_id, year, month, limit=limit, offset=offset
        )
    return await expense_service.list_expense(session, user_id, limit=limit, offset=offset)


@router.get("/summary", response_model=ExpenseSummary)
async def expense_summary_endpoint(
    year: int,
    month: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> ExpenseSummary:
    return await expense_service.get_month_summary(session, user_id, year, month)


@router.get("/trends", response_model=ExpenseTrends)
async def expense_trends_endpoint(
    months: int = Query(default=6, ge=1, le=24),
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> ExpenseTrends:
    return await expense_service.get_trends(session, user_id, months=months)


@router.post("/", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
async def create_expense_endpoint(
    data: ExpenseCreate,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> ExpenseRead:
    try:
        return await expense_service.create_expense(
            session,
            user_id=user_id,
            categories_id=data.categories_id,
            name=data.name,
            amount=data.amount,
            currency=data.currency,
            date=data.date,
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")


@router.get("/{expense_id}", response_model=ExpenseRead)
async def get_expense_endpoint(
    expense_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> ExpenseRead:
    try:
        return await expense_service.get_expense(session, user_id=user_id, expense_id=expense_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Трата не найдена")


@router.patch("/{expense_id}", response_model=ExpenseRead)
async def update_expense_endpoint(
    expense_id: int,
    data: ExpenseUpdate,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> ExpenseRead:
    try:
        return await expense_service.update_expense(
            session,
            user_id=user_id,
            expense_id=expense_id,
            categories_id=data.categories_id,
            name=data.name,
            amount=data.amount,
            currency=data.currency,
            date=data.date,
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Трата или категория не найдены")


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense_endpoint(
    expense_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> None:
    try:
        await expense_service.delete_expense(session, user_id=user_id, expense_id=expense_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Трата не найдена")
