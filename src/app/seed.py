"""Автоматический seed при старте: продукты, стоп-факторы, демо-учётки персон (CLAUDE.md §9), администратор.

Повторный запуск ничего не меняет.

ФИО и ИНН ФЛ совпадают с руководителями персон в симуляторе (`simulator/personas.py`) —
под этими учётками компании персон можно добавить в кабинет. Все данные синтетические.
"""

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.credit.stop_factors import STOP_FACTORS
from app.database import AsyncSessionLocal
from app.enums import ProductType, StaffRole, UserStatus
from app.models import StaffUser
from app.repositories import application as applications_repo
from app.repositories import decision as decisions_repo
from app.repositories import user as users_repo
from app.security import hash_password, verify_password
from app.settings import settings

DEMO_PASSWORD = "demo12345"


@dataclass(frozen=True)
class DemoUser:
    email: str
    last_name: str
    first_name: str
    middle_name: str
    inn_fl: str


DEMO_USERS = [
    # ООО «Северный ветер» 7701234560, ИП 500100000015, ООО «Ромашка» 7705551232
    DemoUser("anna@example.com", "Смирнова", "Анна", "Викторовна", "500100000015"),
    # ИП без долгов, клиент банка — 770700000190
    DemoUser("igor@example.com", "Кузнецов", "Игорь", "Петрович", "770700000190"),
    # ООО «Новый старт» 7801002002 — 4 месяца
    DemoUser("olga@example.com", "Морозова", "Ольга", "Сергеевна", "780100000237"),
    # ООО «Вектор» 5403004007 — просрочка в прошлом
    DemoUser("dmitry@example.com", "Волков", "Дмитрий", "Андреевич", "540300000392"),
    # ООО «Закат» 6605006009 — банкротство
    DemoUser("sergey@example.com", "Лебедев", "Сергей", "Николаевич", "660500000444"),
]


# Условия — CLAUDE.md §9 и витрина фронта (frontend/src/lib/products.ts). Ставки примерные,
# по ним клиент видит ориентировочный платёж; итоговую ставку даст решение по заявке.
CREDIT_PRODUCTS = [
    {
        "code": "WORKING_CAPITAL",
        "name": "Кредит на оборотные средства",
        "product_type": ProductType.TERM_LOAN,
        "min_amount": 300_000,
        "max_amount": 50_000_000,
        "min_term_months": 6,
        "max_term_months": 60,
        "base_rate": 24,
    },
    {
        "code": "CREDIT_LINE",
        "name": "Кредитная линия",
        "product_type": ProductType.CREDIT_LINE,
        "min_amount": 300_000,
        "max_amount": 30_000_000,
        "min_term_months": 6,
        "max_term_months": 18,
        "base_rate": 22,
    },
    {
        "code": "OVERDRAFT",
        "name": "Овердрафт",
        "product_type": ProductType.OVERDRAFT,
        "min_amount": 100_000,
        "max_amount": 10_000_000,
        "min_term_months": 1,
        "max_term_months": 12,
        "base_rate": 26,
    },
    {
        # Нужны данные о залоге — анкеты залога пока нет, продукт скрыт
        "code": "SECURED",
        "name": "Кредит под залог",
        "product_type": ProductType.TERM_LOAN,
        "min_amount": 1_000_000,
        "max_amount": 150_000_000,
        "min_term_months": 12,
        "max_term_months": 120,
        "base_rate": 18,
        "is_active": False,
    },
]


async def seed_products(session: AsyncSession) -> None:
    """Создаёт недостающие продукты; условия существующих не меняет."""
    await applications_repo.ensure_products(
        session, [{"is_active": True, **p} for p in CREDIT_PRODUCTS]
    )
    await session.commit()


async def seed_stop_factors(session: AsyncSession) -> None:
    """Справочник стоп-факторов из кода (`credit/stop_factors.py`): описание всегда свежее."""
    await decisions_repo.ensure_stop_factors(
        session,
        [
            {
                "code": f.code,
                "name": f.name,
                "severity": f.severity,
                "rule_expression": f"{f.rule} → {f.action}",
            }
            for f in STOP_FACTORS
        ],
    )
    await session.commit()


async def seed_demo_users(session: AsyncSession) -> int:
    """Создаёт недостающие демо-учётки; возвращает, сколько создано."""
    created = 0
    for demo in DEMO_USERS:
        if await users_repo.get_user_by_email(session, demo.email) is not None:
            continue
        if await users_repo.get_user_by_inn(session, demo.inn_fl) is not None:
            continue  # ИНН уже занят живой учёткой — не трогаем
        await users_repo.create_user(
            session,
            email=demo.email,
            password_hash=hash_password(DEMO_PASSWORD),
            last_name=demo.last_name,
            first_name=demo.first_name,
            middle_name=demo.middle_name,
            inn_fl=demo.inn_fl,
            phone=None,
            status=UserStatus.ACTIVE,
        )
        created += 1
    await session.commit()
    return created


async def seed_admin(session: AsyncSession) -> str:
    """Суперпользователь /adminuser: логин ADMIN_LOGIN, пароль из ADMIN_PASSWORD (.env).

    Без ADMIN_PASSWORD ничего не создаётся. Смена пароля в .env — новый хэш при следующем старте.
    """
    if not settings.ADMIN_PASSWORD:
        return "ADMIN_PASSWORD не задан — администратор не создан"
    staff = (
        await session.execute(
            select(StaffUser).where(StaffUser.login == settings.ADMIN_LOGIN)
        )
    ).scalar_one_or_none()
    if staff is None:
        staff = (
            await session.execute(
                select(StaffUser).where(StaffUser.email == settings.ADMIN_EMAIL)
            )
        ).scalar_one_or_none()
    if staff is None:
        session.add(
            StaffUser(
                full_name=settings.ADMIN_FULL_NAME,
                email=settings.ADMIN_EMAIL,
                login=settings.ADMIN_LOGIN,
                role=StaffRole.ADMIN,
                is_active=True,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
            )
        )
        result = f"администратор {settings.ADMIN_LOGIN} создан"
    else:
        staff.login = settings.ADMIN_LOGIN
        staff.role = StaffRole.ADMIN
        staff.is_active = True
        if not staff.password_hash or not verify_password(
            settings.ADMIN_PASSWORD, staff.password_hash
        ):
            staff.password_hash = hash_password(settings.ADMIN_PASSWORD)
        result = f"администратор {settings.ADMIN_LOGIN} актуален"
    await session.commit()
    return result


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed_products(session)
        await seed_stop_factors(session)
        created = await seed_demo_users(session)
        admin = await seed_admin(session)
    print(f"seed: демо-учёток создано {created}; {admin}")


if __name__ == "__main__":
    asyncio.run(main())
