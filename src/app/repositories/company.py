import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import CompanyRole, LinkStatus
from app.models import Company, CompanyOkved, CompanyPerson, OkvedCode, UserCompanyLink


async def get_company(session: AsyncSession, company_id: uuid.UUID) -> Company | None:
    return await session.get(Company, company_id)


async def get_company_by_inn(session: AsyncSession, inn: str) -> Company | None:
    stmt = select(Company).where(Company.inn == inn)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def add_company(session: AsyncSession, company: Company) -> Company:
    session.add(company)
    await session.flush()
    return company


async def get_link(
    session: AsyncSession, user_id: uuid.UUID, company_id: uuid.UUID
) -> UserCompanyLink | None:
    stmt = select(UserCompanyLink).where(
        UserCompanyLink.user_id == user_id,
        UserCompanyLink.company_id == company_id,
        UserCompanyLink.status == LinkStatus.CONFIRMED,
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def create_link(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    role: CompanyRole,
    status: LinkStatus,
) -> UserCompanyLink:
    link = UserCompanyLink(
        user_id=user_id, company_id=company_id, role=role, status=status
    )
    session.add(link)
    await session.flush()
    return link


async def list_user_companies(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Company, UserCompanyLink]]:
    stmt = (
        select(Company, UserCompanyLink)
        .join(UserCompanyLink, UserCompanyLink.company_id == Company.id)
        .where(
            UserCompanyLink.user_id == user_id,
            UserCompanyLink.status == LinkStatus.CONFIRMED,
        )
        .order_by(UserCompanyLink.created_at, Company.inn)
    )
    result = await session.execute(stmt)
    return [(company, link) for company, link in result.all()]


async def ensure_okved_codes(
    session: AsyncSession, codes: list[tuple[str, str, str]]
) -> None:
    """Добавляет в справочник ОКВЭД недостающие коды (code, name, section)."""
    if not codes:
        return
    stmt = insert(OkvedCode).values(
        [{"code": c, "name": n, "section": s} for c, n, s in codes]
    )
    await session.execute(stmt.on_conflict_do_nothing(index_elements=["code"]))


async def replace_company_okved(
    session: AsyncSession, company_id: uuid.UUID, codes: list[tuple[str, bool]]
) -> None:
    await session.execute(
        delete(CompanyOkved).where(CompanyOkved.company_id == company_id)
    )
    session.add_all(
        CompanyOkved(company_id=company_id, okved_code=code, is_main=is_main)
        for code, is_main in codes
    )
    await session.flush()


async def list_company_okved(
    session: AsyncSession, company_id: uuid.UUID
) -> list[tuple[str, str, bool]]:
    stmt = (
        select(OkvedCode.code, OkvedCode.name, CompanyOkved.is_main)
        .join(CompanyOkved, CompanyOkved.okved_code == OkvedCode.code)
        .where(CompanyOkved.company_id == company_id)
        .order_by(CompanyOkved.is_main.desc(), OkvedCode.code)
    )
    result = await session.execute(stmt)
    return [(code, name, is_main) for code, name, is_main in result.all()]


async def replace_company_persons(
    session: AsyncSession, company_id: uuid.UUID, persons: list[CompanyPerson]
) -> None:
    await session.execute(
        delete(CompanyPerson).where(CompanyPerson.company_id == company_id)
    )
    session.add_all(persons)
    await session.flush()
