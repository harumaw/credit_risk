import re
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base

SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "schema.dbml"


def test_every_dbml_table_has_a_model():
    dbml_tables = set(
        re.findall(
            r"^Table (\w+)", SCHEMA.read_text(encoding="utf-8"), flags=re.MULTILINE
        )
    )
    assert dbml_tables == set(Base.metadata.tables)


async def test_schema_is_created(db_session: AsyncSession):
    conn = await db_session.connection()
    created = await conn.run_sync(
        lambda sync_conn: set(inspect(sync_conn).get_table_names())
    )
    assert created - {"alembic_version"} == set(Base.metadata.tables)
