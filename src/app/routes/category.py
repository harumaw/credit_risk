from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_session, get_current_user_id
from app.exceptions import AlreadyExistsError, NotFoundError
from app.services import category as category_service
from app.types import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(
    prefix = "/categories",
    tags=["categories"],
)

@router.get("/", response_model=list[CategoryRead])
async def list_categories_endpoint(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
    user_id: int = Depends(get_current_user_id),
) -> list[CategoryRead]:
    return await category_service.list_categories(session, user_id, limit=limit, offset=offset)

@router.post("/", response_model = CategoryRead, status_code = status.HTTP_201_CREATED)
async def create_category_endpoint(data: CategoryCreate, session: AsyncSession  = Depends(get_async_session), 
                                   user_id: int = Depends(get_current_user_id)):
    try:
        return await category_service.create_category(session, user_id = user_id, name = data.name)
    except AlreadyExistsError:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail='Категория с таким названием уже существует'
        )

@router.get("/{category_id}", response_model = CategoryRead)
async def get_category_endpoint(category_id: int, 
                                session: AsyncSession = Depends(get_async_session),
                                user_id: int = Depends(get_current_user_id)):
    try:
        return await category_service.get_category(session, category_id, user_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")


@router.patch("/{category_id}", response_model = CategoryRead)
async def update_category_endpoint(category_id: int, data: CategoryUpdate,
                                session: AsyncSession = Depends(get_async_session),
                                user_id: int = Depends(get_current_user_id)):
    try:
        return await category_service.update_category(session, category_id=category_id, user_id = user_id, name = data.name)
    except NotFoundError:
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Категория не найдена")
    except AlreadyExistsError:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = "Категория с таким названием уже существует"
        )

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_endpoint(category_id: int,
                                   session: AsyncSession = Depends(get_async_session),
                                   user_id: int = Depends(get_current_user_id)):
    try:
        await category_service.delete_category(session, category_id=category_id, user_id = user_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Категория не найдена")
    