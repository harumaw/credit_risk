from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category


async def get_category_by_id(session: AsyncSession, id:int, user_id: int) -> Category | None:
    stmt = select(Category).where(Category.id == id, Category.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_category_by_name(session: AsyncSession, name: str, user_id: int) -> Category | None:
    stmt = select(Category).where(Category.name == name, Category.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def list_categories(
    session: AsyncSession, user_id: int, limit: int = 100, offset: int = 0
) -> list[Category]:
    stmt = (
        select(Category)
        .where(Category.user_id == user_id)
        .order_by(Category.id)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return result.scalars().all()

async def create_category(session: AsyncSession, user_id: int, name: str) -> Category:
    category = Category(user_id=user_id, name=name)
    session.add(category)
    await session.flush()
    await session.refresh(category)
    return category

async def update_category(session: AsyncSession, category: Category, *, name:str | None = None) -> Category:
    if name is not None:
        category.name = name
    await session.flush()
    await session.refresh(category)
    return category

async def delete_category(session: AsyncSession, category: Category):
    await session.delete(category)
    await session.flush()