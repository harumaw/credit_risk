import uuid
from collections.abc import AsyncGenerator
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.enums import StaffRole
from app.integrations.registry import Sources, build_sources
from app.models import StaffUser
from app.security import decode_access_token, decode_staff_token


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> uuid.UUID:
    try:
        return decode_access_token(token)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


staff_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="admin/auth/login")


async def get_current_admin(
    token: str = Depends(staff_oauth2_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> StaffUser:
    """Сотрудник с ролью admin и активной учёткой — иначе 401/403."""
    try:
        staff_id = decode_staff_token(token)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Нужен вход сотрудника",
        )
    staff = await session.get(StaffUser, staff_id)
    if staff is None or not staff.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Сотрудник не найден"
        )
    if staff.role != StaffRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Нужна роль admin"
        )
    return staff


@lru_cache
def get_sources() -> Sources:
    """Клиенты внешних источников (в тестах подменяются через dependency_overrides)."""
    return build_sources()
