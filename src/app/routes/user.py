from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_session, get_current_user_id
from app.exceptions import AlreadyExistsError, InvalidCredentailsError, NotFoundError
from app.rate_limit import limiter
from app.services import auth as auth_service
from app.types import Token, UserLogin, UserRead, UserRegister, UserUpdate

router = APIRouter(
    prefix ="/auth",
    tags=["auth"],
)

@router.post("/register", status_code = status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register_endpoint(
    request: Request, data: UserRegister, session: AsyncSession = Depends(get_async_session)
):
    try:
        await auth_service.register(session, email=data.email, password=data.password)
    except AlreadyExistsError:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = "Пользователь с таким email уже зарегистрирован"
        )

@router.post("/login", response_model = Token)
@limiter.limit("5/minute")
async def login_endpoint(
    request: Request, data: UserLogin, session: AsyncSession = Depends(get_async_session)
):
    try:
        token = await auth_service.login(session, email = data.email, password = data.password)
    except InvalidCredentailsError:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Неверный email или пароль"
        )
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
async def get_me_endpoint(
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
):
    return await auth_service.get_current_user(session, user_id)


@router.patch("/me", response_model=UserRead)
async def update_me_endpoint(
    data: UserUpdate,
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
):
    try:
        return await auth_service.update_base_currency(session, user_id, data.base_currency)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")