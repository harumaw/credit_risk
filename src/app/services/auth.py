from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AlreadyExistsError, NotFoundError, InvalidCredentailsError
from app.models import User
from app.repositories import user as users_repo
import app.security as sec
from app.security import hash_password, verify_password, create_access_token

async def register(session: AsyncSession, email: str, password: str):
    exist_user = await users_repo.get_user_by_email(session, email)
    if exist_user is not None:
        raise AlreadyExistsError

    password_hash = hash_password(password)
    user = await users_repo.create_user(session, email= email, password_hash = password_hash)
    await session.commit()
    return user


async def login(session: AsyncSession, email: str, password: str) -> str:
    user = await users_repo.get_user_by_email(session, email)
    if user is None:
        raise InvalidCredentailsError

    if not verify_password(password, user.password_hash):
        raise InvalidCredentailsError

    return create_access_token(user.id)


async def get_current_user(session: AsyncSession, user_id: int) -> User:
    user = await users_repo.get_user_by_id(session, user_id)
    if user is None:
        raise NotFoundError
    return user


async def update_base_currency(session: AsyncSession, user_id: int, base_currency: str) -> User:
    user = await users_repo.get_user_by_id(session, user_id)
    if user is None:
        raise NotFoundError

    user = await users_repo.update_base_currency(session, user, base_currency)
    await session.commit()
    return user
