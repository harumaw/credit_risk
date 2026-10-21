"""Автоматический seed при старте: демо-учётки персон (CLAUDE.md §9). Повторный запуск ничего не меняет.

ФИО и ИНН ФЛ совпадают с руководителями персон в симуляторе (`simulator/personas.py`) —
под этими учётками компании персон можно добавить в кабинет. Все данные синтетические.
"""

import asyncio
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.enums import UserStatus
from app.repositories import user as users_repo
from app.security import hash_password

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


async def main() -> None:
    async with AsyncSessionLocal() as session:
        created = await seed_demo_users(session)
    print(f"seed: демо-учёток создано {created}")


if __name__ == "__main__":
    asyncio.run(main())
