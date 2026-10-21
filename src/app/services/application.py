"""Кабинет: заявки на кредит — продукты, отправка анкеты, список и карточка заявки.

Решение по заявке (скоринг, лимит, контрпредложение) — следующий шаг конвейера:
сейчас заявка сохраняется в статусе `submitted` и ждёт рассмотрения.
"""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ApplicationStatus, ConsentType
from app.exceptions import FieldValueError, NotFoundError
from app.models import (
    ApplicationStatusHistory,
    Company,
    Consent,
    CreditProduct,
    LoanApplication,
)
from app.repositories import application as applications_repo
from app.repositories import company as companies_repo
from app.types import (
    Application,
    ApplicationCreate,
    ApplicationDetails,
    ApplicationEvent,
    CreditProductRead,
)

CONSENT_TEXT_VERSION = "2026-10"

# Статус в БД → статус и подпись для клиента
_CLIENT_STATUS: dict[ApplicationStatus, tuple[str, str]] = {
    ApplicationStatus.DRAFT: ("draft", "Черновик"),
    ApplicationStatus.SUBMITTED: ("submitted", "Заявка отправлена"),
    ApplicationStatus.DATA_COLLECTION: ("checking", "Собираем данные"),
    ApplicationStatus.SCORING: ("checking", "Оцениваем заявку"),
    ApplicationStatus.MANUAL_REVIEW: ("checking", "На рассмотрении у специалиста"),
    ApplicationStatus.APPROVED: ("approved", "Одобрено"),
    ApplicationStatus.OFFER_ACCEPTED: ("approved", "Условия приняты"),
    ApplicationStatus.CONTRACT_SIGNED: ("approved", "Договор подписан"),
    ApplicationStatus.ISSUED: ("issued", "Кредит выдан"),
    ApplicationStatus.DECLINED: ("rejected", "Отказ"),
    ApplicationStatus.CANCELLED: ("rejected", "Заявка отменена"),
}
_NOTE = {
    "draft": "Заявка не отправлена — заполните и отправьте анкету",
    "submitted": "Заявка отправлена. Решение появится здесь — мы сообщим в кабинете",
    "checking": "Банк проверяет данные компании",
    "approved": "Банк одобрил заявку",
    "issued": "Деньги перечислены на счёт",
    "rejected": "По заявке принято отрицательное решение",
}


def _rub(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _company_name(company: Company) -> str:
    return company.short_name or company.full_name


def _product(p: CreditProduct) -> CreditProductRead:
    return CreditProductRead(
        code=p.code,
        name=p.name,
        kind=p.product_type.value,
        min_amount=_rub(p.min_amount) or 0,
        max_amount=_rub(p.max_amount) or 0,
        min_term_months=p.min_term_months or 1,
        max_term_months=p.max_term_months or 1,
        rate=float(p.base_rate or 0),
    )


def _application(
    a: LoanApplication, company: Company, product: CreditProduct
) -> Application:
    status = _CLIENT_STATUS[a.status][0]
    return Application(
        id=a.id,
        number=a.number,
        company_id=company.id,
        company_name=_company_name(company),
        created_at=a.created_at.date(),
        product=product.name,
        product_code=product.code,
        amount=_rub(a.requested_amount),
        term_months=a.requested_term_months,
        purpose=a.purpose,
        status=status,
        note=_NOTE.get(status, ""),
    )


def _check_conditions(data: ApplicationCreate, product: CreditProduct) -> None:
    """Сумма и срок — в пределах условий продукта."""
    lo, hi = _rub(product.min_amount), _rub(product.max_amount)
    if (lo is not None and data.amount < lo) or (hi is not None and data.amount > hi):
        raise FieldValueError(
            "amount",
            f"Сумма по этому продукту — от {lo:,} до {hi:,} ₽".replace(",", " "),
        )
    t_lo, t_hi = product.min_term_months, product.max_term_months
    if (t_lo is not None and data.term_months < t_lo) or (
        t_hi is not None and data.term_months > t_hi
    ):
        raise FieldValueError(
            "termMonths", f"Срок по этому продукту — от {t_lo} до {t_hi} мес"
        )


# --- Чтение -----------------------------------------------------------------


async def list_products(session: AsyncSession) -> list[CreditProductRead]:
    return [_product(p) for p in await applications_repo.list_active_products(session)]


async def list_applications(
    session: AsyncSession, user_id: uuid.UUID
) -> list[Application]:
    rows = await applications_repo.list_user_applications(session, user_id)
    return [_application(*row) for row in rows]


async def application_details(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> ApplicationDetails:
    row = await applications_repo.get_user_application(session, user_id, application_id)
    if row is None:
        raise NotFoundError  # чужая заявка неотличима от несуществующей
    history = await applications_repo.list_history(session, application_id)
    events = [
        ApplicationEvent(
            status=_CLIENT_STATUS[h.to_status][0],
            label=_CLIENT_STATUS[h.to_status][1],
            at=h.changed_at,
            comment=h.comment,
        )
        for h in history
    ]
    return ApplicationDetails(**_application(*row).model_dump(), history=events)


# --- Отправка ---------------------------------------------------------------


async def submit(
    session: AsyncSession, user_id: uuid.UUID, data: ApplicationCreate
) -> ApplicationDetails:
    company = await companies_repo.get_company(session, data.company_id)
    if (
        company is None
        or await companies_repo.get_link(session, user_id, company.id) is None
    ):
        raise FieldValueError("companyId", "Выберите компанию из своего кабинета")
    product = await applications_repo.get_active_product(session, data.product_code)
    if product is None:
        raise FieldValueError("productCode", "Такого продукта нет — выберите из списка")
    _check_conditions(data, product)

    now = datetime.now(UTC)
    application = LoanApplication(
        number=await applications_repo.next_number(session),
        company_id=company.id,
        applicant_user_id=user_id,
        product_id=product.id,
        requested_amount=Decimal(data.amount),
        requested_term_months=data.term_months,
        purpose=data.purpose,
        form_step=1,
        status=ApplicationStatus.SUBMITTED,
        submitted_at=now,
    )
    history = ApplicationStatusHistory(
        from_status=None,
        to_status=ApplicationStatus.SUBMITTED,
        changed_by_user_id=user_id,
        comment="Анкета заполнена и отправлена клиентом",
    )
    consents = [
        Consent(
            user_id=user_id,
            company_id=company.id,
            consent_type=kind,
            text_version=CONSENT_TEXT_VERSION,
            signed_at=now,
        )
        for kind in (ConsentType.PERSONAL_DATA, ConsentType.BKI_REQUEST)
    ]
    application = await applications_repo.add_application(
        session, application, history, consents
    )
    await session.commit()
    return await application_details(session, user_id, application.id)
