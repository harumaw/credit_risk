"""Схема поднимается миграциями в PostgreSQL — проверяем, что она совпадает с моделями."""

import uuid

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base
from tests.helpers import make_inn_fl


async def test_migrations_match_models(db_session: AsyncSession):
    # То же, что `alembic check`: модель поменяли без миграции — тест красный
    conn = await db_session.connection()
    diff = await conn.run_sync(
        lambda sync_conn: compare_metadata(
            MigrationContext.configure(sync_conn), Base.metadata
        )
    )
    assert diff == []


async def test_native_enum_rejects_unknown_value(db_session: AsyncSession):
    # Статус — native enum PostgreSQL: мимо ORM чужое значение не записать
    with pytest.raises(DBAPIError, match="user_status"):
        await db_session.execute(
            text(
                "INSERT INTO users (id, last_name, first_name, inn_fl, status) "
                "VALUES (:id, 'Иванов', 'Иван', :inn, 'deleted')"
            ),
            {"id": str(uuid.uuid4()), "inn": make_inn_fl(1)},
        )
