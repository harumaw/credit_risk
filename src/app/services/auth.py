import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import UserStatus
from app.exceptions import (
    AlreadyExistsError,
    InvalidCredentailsError,
    NotFoundError,
    UserBlockedError,
)
from app.models import User
from app.repositories import user as users_repo
from app.security import create_access_token, hash_password, verify_password
from app.types import UserRegister


async def register(session: AsyncSession, data: UserRegister) -> User:
    if await users_repo.get_user_by_email(session, data.email) is not None:
        raise AlreadyExistsError("email")
    if await users_repo.get_user_by_inn(session, data.inn_fl) is not None:
        raise AlreadyExistsError("inn_fl")
    if (
        data.phone
        and await users_repo.get_user_by_phone(session, data.phone) is not None
    ):
        raise AlreadyExistsError("phone")

    try:
        user = await users_repo.create_user(
            session,
            email=data.email,
            password_hash=hash_password(data.password),
            last_name=data.last_name,
            first_name=data.first_name,
            middle_name=data.middle_name,
            inn_fl=data.inn_fl,
            phone=data.phone,
            # Внешней верификации (ЕСИА/УКЭП) пока нет — учётка активна сразу
            status=UserStatus.ACTIVE,
        )
        await session.commit()
    except IntegrityError:
        # Параллельная регистрация с теми же данными проскочила между проверкой и вставкой
        await session.rollback()
        raise AlreadyExistsError from None
    return user


async def login(session: AsyncSession, email: str, password: str) -> str:
    user = await users_repo.get_user_by_email(session, email)
    # password_hash пуст у пользователей, пришедших через ЕСИА/УКЭП — по паролю они не входят
    if user is None or user.password_hash is None:
        raise InvalidCredentailsError

    if not verify_password(password, user.password_hash):
        raise InvalidCredentailsError

    if user.status == UserStatus.BLOCKED:
        raise UserBlockedError

    return create_access_token(user.id)


async def get_current_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await users_repo.get_user_by_id(session, user_id)
    if user is None:
        raise NotFoundError
    return user
