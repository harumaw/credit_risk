import uuid

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import LinkStatus
from app.models import (
    APPLICATION_NUMBER_SEQ,
    ApplicationStatusHistory,
    Company,
    Consent,
    CreditProduct,
    LoanApplication,
    UserCompanyLink,
)
from app.sandbox import SANDBOX_INNS


async def ensure_products(session: AsyncSession, products: list[dict]) -> None:
    """Добавляет в справочник недостающие продукты (по code), существующие не трогает."""
    stmt = insert(CreditProduct).values(products)
    await session.execute(stmt.on_conflict_do_nothing(index_elements=["code"]))


async def list_active_products(session: AsyncSession) -> list[CreditProduct]:
    stmt = (
        select(CreditProduct)
        .where(CreditProduct.is_active.is_(True))
        .order_by(CreditProduct.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_active_product(session: AsyncSession, code: str) -> CreditProduct | None:
    stmt = select(CreditProduct).where(
        CreditProduct.code == code, CreditProduct.is_active.is_(True)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def next_number(session: AsyncSession) -> str:
    return str(await session.scalar(APPLICATION_NUMBER_SEQ.next_value()))


async def add_application(
    session: AsyncSession,
    application: LoanApplication,
    history: ApplicationStatusHistory,
    consents: list[Consent],
) -> LoanApplication:
    session.add(application)
    await session.flush()
    history.application_id = application.id
    for consent in consents:
        consent.application_id = application.id
    session.add_all([history, *consents])
    await session.flush()
    await session.refresh(application)
    return application


# Заявка, название компании и продукта — то, что показываем в кабинете
ApplicationRow = tuple[LoanApplication, Company, CreditProduct]


def _rows_for_user(user_id: uuid.UUID):
    # Заявки видят все, кто подтверждённо связан с компанией, а не только автор;
    # у компаний песочницы связей много (у каждого проверяющего своя) — там только автор
    return (
        select(LoanApplication, Company, CreditProduct)
        .join(Company, Company.id == LoanApplication.company_id)
        .join(CreditProduct, CreditProduct.id == LoanApplication.product_id)
        .join(UserCompanyLink, UserCompanyLink.company_id == Company.id)
        .where(
            UserCompanyLink.user_id == user_id,
            UserCompanyLink.status == LinkStatus.CONFIRMED,
            or_(
                Company.inn.not_in(SANDBOX_INNS),
                LoanApplication.applicant_user_id == user_id,
            ),
        )
    )


async def list_user_applications(
    session: AsyncSession, user_id: uuid.UUID
) -> list[ApplicationRow]:
    # created_at в одной транзакции совпадает — порядок добирает номер
    stmt = _rows_for_user(user_id).order_by(
        LoanApplication.created_at.desc(), LoanApplication.number.desc()
    )
    result = await session.execute(stmt)
    return [(a, c, p) for a, c, p in result.all()]


async def get_user_application(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> ApplicationRow | None:
    stmt = _rows_for_user(user_id).where(LoanApplication.id == application_id)
    row = (await session.execute(stmt)).first()
    return (row[0], row[1], row[2]) if row else None


async def list_history(
    session: AsyncSession, application_id: uuid.UUID
) -> list[ApplicationStatusHistory]:
    stmt = (
        select(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == application_id)
        .order_by(ApplicationStatusHistory.changed_at, ApplicationStatusHistory.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_idempotency_key(
    session: AsyncSession, user_id: uuid.UUID, key: str
) -> LoanApplication | None:
    stmt = select(LoanApplication).where(
        LoanApplication.applicant_user_id == user_id,
        LoanApplication.idempotency_key == key,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def lock_application(
    session: AsyncSession, application_id: uuid.UUID
) -> LoanApplication | None:
    """Заявка под блокировкой строки: смены статуса из API и воркера не перемешаются."""
    stmt = (
        select(LoanApplication)
        .where(LoanApplication.id == application_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_application_row(
    session: AsyncSession, application_id: uuid.UUID
) -> ApplicationRow | None:
    stmt = (
        select(LoanApplication, Company, CreditProduct)
        .join(Company, Company.id == LoanApplication.company_id)
        .join(CreditProduct, CreditProduct.id == LoanApplication.product_id)
        .where(LoanApplication.id == application_id)
    )
    row = (await session.execute(stmt)).first()
    return (row[0], row[1], row[2]) if row else None


async def add_history(session: AsyncSession, row: ApplicationStatusHistory) -> None:
    session.add(row)
    await session.flush()


async def history_after(
    session: AsyncSession, application_id: uuid.UUID, after_id: int
) -> list[ApplicationStatusHistory]:
    stmt = (
        select(ApplicationStatusHistory)
        .where(
            ApplicationStatusHistory.application_id == application_id,
            ApplicationStatusHistory.id > after_id,
        )
        .order_by(ApplicationStatusHistory.id)
    )
    return list((await session.execute(stmt)).scalars())
