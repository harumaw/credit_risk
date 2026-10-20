import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_session, get_current_user_id
from app.exceptions import (
    AlreadyExistsError,
    InvalidCredentailsError,
    NotFoundError,
    UserBlockedError,
)
from app.rate_limit import limiter
from app.services import auth as auth_service
from app.types import Token, UserLogin, UserRead, UserRegister

_DUPLICATE_MESSAGES = {
    "email": "Пользователь с таким email уже зарегистрирован",
    "inn_fl": "Пользователь с таким ИНН уже зарегистрирован",
    "phone": "Пользователь с таким телефоном уже зарегистрирован",
}

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserRead)
@limiter.limit("3/minute")
async def register_endpoint(
    request: Request,
    data: UserRegister,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await auth_service.register(session, data)
    except AlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_DUPLICATE_MESSAGES.get(
                exc.field, "Пользователь уже зарегистрирован"
            ),
        )


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login_endpoint(
    request: Request,
    data: UserLogin,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        token = await auth_service.login(
            session, email=data.email, password=data.password
        )
    except InvalidCredentailsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль"
        )
    except UserBlockedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Учётная запись заблокирована"
        )
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
async def get_me_endpoint(
    session: AsyncSession = Depends(get_async_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    try:
        return await auth_service.get_current_user(session, user_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден"
        )
