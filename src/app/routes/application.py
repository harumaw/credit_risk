import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.credit.statuses import TransitionError
from app.dependencies import get_async_session, get_current_user_id
from app.exceptions import ConflictError, FieldValueError, NotFoundError
from app.services import application as application_service
from app.settings import settings
from app.types import (
    AcceptRequest,
    Application,
    ApplicationCreate,
    ApplicationDetails,
    CreditProductRead,
    SignCode,
    SignRequest,
)

router = APIRouter(prefix="/applications", tags=["applications"])

NOT_FOUND = "Заявка не найдена"
PING_EVERY = 15  # секунд без событий — комментарий-пинг, чтобы прокси не рвали поток


def _field_error(exc: FieldValueError) -> HTTPException:
    # Та же форма, что у ошибок валидации FastAPI, — фронт покажет текст у поля
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[
            {"loc": ["body", exc.field], "msg": exc.message, "type": "value_error"}
        ],
    )


def _conflict(exc: TransitionError) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        f"Действие недоступно в текущем статусе заявки ({exc.current.value})",
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
    idempotency_key: str | None = Header(default=None, max_length=64),
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    try:
        return await application_service.submit(session, user_id, data, idempotency_key)
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)


@router.post("/{application_id}/accept", response_model=ApplicationDetails)
async def accept_endpoint(
    application_id: uuid.UUID,
    data: AcceptRequest | None = None,
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    offer_index = data.offer_index if data else 0
    try:
        return await application_service.accept(
            session, user_id, application_id, offer_index
        )
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    except TransitionError as exc:
        raise _conflict(exc) from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.reason) from None
    except FieldValueError as exc:
        raise _field_error(exc) from None


@router.post("/{application_id}/sign-code", response_model=SignCode)
async def sign_code_endpoint(
    application_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    try:
        return await application_service.sign_code(session, user_id, application_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    except TransitionError as exc:
        raise _conflict(exc) from None


@router.post("/{application_id}/sign", response_model=ApplicationDetails)
async def sign_endpoint(
    application_id: uuid.UUID,
    data: SignRequest,
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    try:
        return await application_service.sign(
            session, user_id, application_id, data.code
        )
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    except TransitionError as exc:
        raise _conflict(exc) from None
    except FieldValueError as exc:
        raise _field_error(exc) from None


@router.post("/{application_id}/cancel", response_model=ApplicationDetails)
async def cancel_endpoint(
    application_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    try:
        return await application_service.cancel(session, user_id, application_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    except TransitionError as exc:
        raise _conflict(exc) from None


@router.get("/{application_id}/events")
async def events_endpoint(
    application_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    """SSE: `event: status` на каждую смену статуса; поток закрывается после финального."""
    try:
        await application_service.ensure_visible(session, user_id, application_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    async def stream() -> AsyncIterator[str]:
        idle = 0.0
        poll = settings.EVENTS_POLL_SECONDS
        max_polls = max(1, int(settings.EVENTS_MAX_SECONDS / poll))
        async for event in application_service.events(
            session, application_id, poll, max_polls, asyncio.sleep
        ):
            if event is not None:
                idle = 0.0
                yield f"event: status\ndata: {event.model_dump_json(by_alias=True)}\n\n"
                continue
            idle += poll
            if idle >= PING_EVERY:
                idle = 0.0
                yield ": ping\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
