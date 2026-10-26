"""API кабинета администратора (/adminuser во фронте). Только сотрудник с ролью admin."""

import csv
import io
import random
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_session, get_current_admin
from app.enums import ApplicationStatus
from app.exceptions import InvalidCredentailsError, NotFoundError
from app.models import StaffUser
from app.rate_limit import limiter
from app.repositories.admin import SORTS, ApplicationFilters, CompanyFilters
from app.services import admin as admin_service
from app.services.scoring import NoScoringModel

router = APIRouter(prefix="/admin", tags=["admin"])


class StaffLogin(BaseModel):
    login: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class CalculateRequest(BaseModel):
    features: dict[str, Any]


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def company_filters(
    q: str | None = None,
    decision: str | None = None,
    segment: str | None = None,
    model: str | None = None,
    grade: str | None = Query(None, description="один или через запятую: A,B"),
    fact: str | None = Query(None, pattern="^(default|no_default|unknown)$"),
    source: str | None = Query(None, pattern="^(synthetic|live)$"),
    score_min: float | None = None,
    score_max: float | None = None,
    as_of_from: date | None = None,
    as_of_to: date | None = None,
    borderline: float | None = Query(None, ge=0, le=50),
    hard_stop: bool | None = None,
) -> CompanyFilters:
    return CompanyFilters(
        q,
        decision,
        segment,
        model,
        grade,
        fact,
        source,
        score_min,
        score_max,
        as_of_from,
        as_of_to,
        borderline,
        hard_stop,
    )


def _prefixed(request: Request, prefix: str) -> CompanyFilters:
    """Второй набор фильтров (эталон для сравнения) — параметры с префиксом ref_."""
    p = request.query_params

    def get(name):
        v = p.get(prefix + name)
        return v if v not in (None, "") else None

    def fl(name):
        v = get(name)
        return float(v) if v is not None else None

    hs = get("hard_stop")
    return CompanyFilters(
        q=get("q"),
        decision=get("decision"),
        segment=get("segment"),
        model=get("model"),
        grade=get("grade"),
        fact=get("fact"),
        source=get("source"),
        score_min=fl("score_min"),
        score_max=fl("score_max"),
        as_of_from=date.fromisoformat(get("as_of_from")) if get("as_of_from") else None,
        as_of_to=date.fromisoformat(get("as_of_to")) if get("as_of_to") else None,
        borderline=fl("borderline"),
        hard_stop=None if hs is None else hs == "true",
    )


# --------------------------------------------------------------- вход


@router.post("/auth/login")
@limiter.limit("5/minute")
async def admin_login_endpoint(
    request: Request,
    data: StaffLogin,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        token, staff = await admin_service.login(
            session, data.login, data.password, _ip(request)
        )
    except InvalidCredentailsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль"
        )
    return {
        "access_token": token,
        "token_type": "bearer",
        "staff": admin_service.staff_view(staff),
    }


@router.get("/me")
async def admin_me_endpoint(staff: StaffUser = Depends(get_current_admin)):
    return admin_service.staff_view(staff)


# --------------------------------------------------------------- компании


@router.get("/summary")
async def summary_endpoint(
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    return await admin_service.summary(session)


@router.get("/companies")
async def companies_endpoint(
    filters: CompanyFilters = Depends(company_filters),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort: str = Query("-as_of"),
    random_sample: bool = Query(False, alias="random"),
    seed: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    if sort not in SORTS:
        raise HTTPException(status_code=422, detail=f"sort: одно из {sorted(SORTS)}")
    used_seed = (
        (seed if seed is not None else random.randint(1, 999_999))
        if random_sample
        else None
    )
    data = await admin_service.list_companies(
        session,
        filters,
        limit=limit,
        offset=0 if random_sample else offset,
        sort=sort,
        random_seed=used_seed,
    )
    data["seed"] = used_seed
    return data


CSV_COLUMNS = [
    "name",
    "inn",
    "legalForm",
    "msp",
    "region",
    "source",
    "segment",
    "model",
    "modelVersion",
    "score",
    "grade",
    "pd",
    "decisionLabel",
    "fact",
    "asOf",
    "scoredAt",
]


@router.get("/companies.csv")
async def companies_csv_endpoint(
    filters: CompanyFilters = Depends(company_filters),
    limit: int = Query(5000, ge=1, le=20000),
    sort: str = Query("-as_of"),
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    if sort not in SORTS:
        raise HTTPException(status_code=422, detail="sort")
    data = await admin_service.list_companies(
        session, filters, limit=limit, offset=0, sort=sort, random_seed=None
    )
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=CSV_COLUMNS, extrasaction="ignore", delimiter=";"
    )
    writer.writeheader()
    writer.writerows(data["items"])
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="companies.csv"'},
    )


@router.get("/companies/{company_id}")
async def company_endpoint(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    try:
        return await admin_service.company_card(session, company_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Компания не найдена")


@router.post("/companies/{company_id}/score")
async def rescore_endpoint(
    request: Request,
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    staff: StaffUser = Depends(get_current_admin),
):
    try:
        return await admin_service.rescore(session, staff, company_id, _ip(request))
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    except NoScoringModel:
        raise HTTPException(
            status_code=409,
            detail="Модели скоринга не загружены: python -m app.dataload.synthetic --models-only",
        )


# --------------------------------------------------------------- заявки


@router.get("/applications")
async def applications_endpoint(
    q: str | None = Query(None, description="номер заявки, ИНН или название"),
    company_id: uuid.UUID | None = None,
    app_status: str | None = Query(None, alias="status"),
    decision: str | None = Query(
        None, pattern="^(approve|counter_offer|manual_review|decline|none)$"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    if app_status and app_status not in {s.value for s in ApplicationStatus}:
        raise HTTPException(status_code=422, detail="status: неизвестный статус заявки")
    return await admin_service.list_applications(
        session,
        ApplicationFilters(q or None, company_id, app_status, decision),
        limit=limit,
        offset=offset,
    )


@router.get("/applications/{application_id}")
async def application_endpoint(
    application_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    """Заявка целиком: условия, решение с баллами и PD, разбор скоринга, источники, история."""
    try:
        return await admin_service.application_card(session, application_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Заявка не найдена")


# --------------------------------------------------------------- модели


@router.get("/models")
async def models_endpoint(
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    return await admin_service.list_models(session)


@router.get("/models/{model_id}")
async def model_endpoint(
    model_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    try:
        return await admin_service.model_detail(session, model_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Модель не найдена")


@router.post("/models/{model_id}/calculate")
async def calculate_endpoint(
    model_id: uuid.UUID,
    data: CalculateRequest,
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    try:
        return await admin_service.calculate(session, model_id, data.features)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Модель не найдена")


@router.get("/example")
async def example_endpoint(
    filters: CompanyFilters = Depends(company_filters),
    seed: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    """Случайная оскоренная компания под фильтры — подставить её признаки в калькулятор."""
    found = await admin_service.example(
        session, filters, seed if seed is not None else random.randint(1, 999_999)
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Под условия никто не подходит")
    return found


# --------------------------------------------------------------- срезы


@router.get("/analysis/matrix")
async def matrix_endpoint(
    filters: CompanyFilters = Depends(company_filters),
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    return await admin_service.matrix(session, filters)


@router.get("/analysis/drivers")
async def drivers_endpoint(
    request: Request,
    filters: CompanyFilters = Depends(company_filters),
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    """Чем группа (фильтры) отличается от эталона (параметры ref_*; по умолчанию — одобренные)."""
    reference = _prefixed(request, "ref_")
    if not any(vars(reference).values()):
        reference = CompanyFilters(decision="approve")
    return await admin_service.drivers(session, filters, reference)


@router.get("/analysis/disagreement")
async def disagreement_endpoint(
    filters: CompanyFilters = Depends(company_filters),
    sample: int = Query(300, ge=10, le=2000),
    seed: int | None = None,
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    """Champion / challenger: решения всех моделей на одной случайной выборке."""
    return await admin_service.disagreement(
        session,
        filters,
        seed if seed is not None else random.randint(1, 999_999),
        sample,
    )


@router.get("/analysis/monthly")
async def monthly_endpoint(
    filters: CompanyFilters = Depends(company_filters),
    session: AsyncSession = Depends(get_async_session),
    _: StaffUser = Depends(get_current_admin),
):
    return await admin_service.monthly(session, filters)
