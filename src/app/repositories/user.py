import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import UserStatus
from app.models import User


async def get_user_by_id(session: AsyncSession, id: uuid.UUID) -> User | None:
    stmt = select(User).where(User.id == id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str,
    last_name: str,
    first_name: str,
    middle_name: str | None,
    inn_fl: str,
    phone: str | None,
    status: UserStatus,
) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        last_name=last_name,
        first_name=first_name,
        middle_name=middle_name,
        inn_fl=inn_fl,
        phone=phone,
        status=status,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_inn(session: AsyncSession, inn_fl: str) -> User | None:
    stmt = select(User).where(User.inn_fl == inn_fl)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_phone(session: AsyncSession, phone: str) -> User | None:
    stmt = select(User).where(User.phone == phone)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
