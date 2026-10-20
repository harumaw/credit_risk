from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AlreadyExistsError, NotFoundError
from app.models import Category
from app.repositories import category as category_repo

async def create_category(session: AsyncSession, user_id: int, name: str) -> Category:
    exist_category = await category_repo.get_category_by_name(session, name, user_id)
    if exist_category is not None:
        raise AlreadyExistsError

    category = await category_repo.create_category(session, user_id, name)
    await session.commit()
    return category

async def get_category(session: AsyncSession, category_id: int, user_id: int) -> Category:
    category = await category_repo.get_category_by_id(session, category_id, user_id)
    if category is None:
        raise NotFoundError
    return category

async def update_category(session: AsyncSession, category_id: int, user_id: int, *, name: str | None = None) -> Category:
    category = await category_repo.get_category_by_id(session, category_id, user_id)

    if category is None:
        raise NotFoundError

    if name is not None:
        existing = await category_repo.get_category_by_name(session, name, user_id)
        if existing is not None and existing.id != category.id:
            raise AlreadyExistsError

    category = await category_repo.update_category(session, category, name = name)
    await session.commit()
    return category

async def list_categories(
    session: AsyncSession, user_id: int, limit: int = 100, offset: int = 0
) -> list[Category]:
    return await category_repo.list_categories(session, user_id, limit=limit, offset=offset)

async def delete_category(session: AsyncSession, category_id: int, user_id: int) -> None:
    category = await category_repo.get_category_by_id(session, category_id, user_id)

    if category is None:
        raise NotFoundError

    await category_repo.delete_category(session, category)
    await session.commit()
    