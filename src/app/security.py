from datetime import datetime, timedelta, UTC

import jwt
from passlib.context import CryptContext

from app.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated = "auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str):
    return pwd_context.verify(password, password_hash)

def create_access_token(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> int:
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    return int(payload["sub"])