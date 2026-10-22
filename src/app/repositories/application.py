import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import LinkStatus
from app.models import (
    ApplicationStatusHistory,
    Company,
    Consent,
    CreditProduct,
    LoanApplication,
    UserCompanyLink,
)

FIRST_NUMBER = 1001  # номера заявок — 1001, 1002, … (видны клиенту)


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
    result = await session.execute(select(func.count()).select_from(LoanApplication))
    return str(FIRST_NUMBER + result.scalar_one())


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
    # Заявки видят все, кто подтверждённо связан с компанией, а не только автор
    return (
        select(LoanApplication, Company, CreditProduct)
        .join(Company, Company.id == LoanApplication.company_id)
        .join(CreditProduct, CreditProduct.id == LoanApplication.product_id)
        .join(UserCompanyLink, UserCompanyLink.company_id == Company.id)
        .where(
            UserCompanyLink.user_id == user_id,
            UserCompanyLink.status == LinkStatus.CONFIRMED,
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
