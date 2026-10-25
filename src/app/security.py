import uuid
from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from app.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str):
    return pwd_context.verify(password, password_hash)


STAFF_KIND = "staff"  # токен сотрудника; клиентский — без поля kind
STAFF_TOKEN_MINUTES = 12 * 60


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    """Токен клиента. Токен сотрудника сюда не подходит — кабинеты разделены."""
    payload = jwt.decode(
        token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("kind") is not None:
        raise ValueError("not a client token")
    return uuid.UUID(payload["sub"])


def create_staff_token(staff_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=STAFF_TOKEN_MINUTES)
    payload = {"sub": str(staff_id), "kind": STAFF_KIND, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_staff_token(token: str) -> uuid.UUID:
    payload = jwt.decode(
        token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("kind") != STAFF_KIND:
        raise ValueError("not a staff token")
    return uuid.UUID(payload["sub"])
