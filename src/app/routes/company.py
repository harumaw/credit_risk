import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_session, get_current_user_id, get_sources
from app.exceptions import AlreadyExistsError, ForbiddenError, NotFoundError
from app.integrations.base import SourceNotFoundError, SourceUnavailableError
from app.integrations.registry import Sources
from app.services import company as company_service
from app.types import (
    CompanyAdded,
    CompanyBrief,
    CompanyLookup,
    CompanySummary,
    GroupSummary,
    InnRequest,
)

router = APIRouter(prefix="/companies", tags=["companies"])

_NOT_FOUND = "Компания не найдена"


def _registry_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SourceNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Компания с таким ИНН не найдена в реестре",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Реестр ЕГРЮЛ временно недоступен, попробуйте позже",
    )


@router.get("", response_model=list[CompanyBrief])
async def list_companies_endpoint(
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return await company_service.list_companies(session, user_id)


@router.post("/lookup", response_model=CompanyLookup)
async def lookup_company_endpoint(
    data: InnRequest,
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
    sources: Sources = Depends(get_sources),
):
    try:
        return await company_service.lookup(session, sources, user_id, data.inn)
    except (SourceNotFoundError, SourceUnavailableError) as exc:
        raise _registry_error(exc) from None
    except NotFoundError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CompanyAdded)
async def add_company_endpoint(
    data: InnRequest,
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
    sources: Sources = Depends(get_sources),
):
    try:
        return await company_service.add(session, sources, user_id, data.inn)
    except (SourceNotFoundError, SourceUnavailableError) as exc:
        raise _registry_error(exc) from None
    except AlreadyExistsError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Компания уже есть в кабинете")
    except ForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, exc.reason)
    except NotFoundError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")


@router.get("/group-summary", response_model=GroupSummary)
async def group_summary_endpoint(
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return await company_service.group_summary(session, user_id)


@router.get("/{company_id}/summary", response_model=CompanySummary)
async def company_summary_endpoint(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    try:
        return await company_service.company_summary(session, user_id, company_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
