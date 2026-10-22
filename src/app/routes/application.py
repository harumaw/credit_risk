import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_session, get_current_user_id
from app.exceptions import FieldValueError, NotFoundError
from app.services import application as application_service
from app.types import (
    Application,
    ApplicationCreate,
    ApplicationDetails,
    CreditProductRead,
)

router = APIRouter(prefix="/applications", tags=["applications"])


def _field_error(exc: FieldValueError) -> HTTPException:
    # Та же форма, что у ошибок валидации FastAPI, — фронт покажет текст у поля
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[
            {"loc": ["body", exc.field], "msg": exc.message, "type": "value_error"}
        ],
    )


@router.get("/products", response_model=list[CreditProductRead])
async def list_products_endpoint(
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return await application_service.list_products(session)


@router.get("", response_model=list[Application])
async def list_applications_endpoint(
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return await application_service.list_applications(session, user_id)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApplicationDetails)
async def submit_application_endpoint(
    data: ApplicationCreate,
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    try:
        return await application_service.submit(session, user_id, data)
    except FieldValueError as exc:
        raise _field_error(exc) from None


@router.get("/{application_id}", response_model=ApplicationDetails)
async def application_details_endpoint(
    application_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    try:
        return await application_service.application_details(
            session, user_id, application_id
        )
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
