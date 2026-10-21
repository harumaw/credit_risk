import os

# Тесты идут на PostgreSQL 16, в отдельной базе (по умолчанию app_test в Postgres из docker compose).
TEST_DATABASE_URL = os.environ.setdefault(
    "TEST_DATABASE_URL", "postgresql+asyncpg://app:secret@localhost:5432/app_test"
)
# settings и alembic/env.py берут URL из POSTGRES_DSN — подменяем, чтобы не задеть рабочую базу
os.environ["POSTGRES_DSN"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-tests-only-0123456789")

from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.dependencies import get_async_session, get_sources
from app.integrations.registry import Sources, build_sources
from app.main import app
from app.rate_limit import limiter
from simulator.main import app as simulator_app
from tests.helpers import registration_payload

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _recreate_database(url: str) -> None:
    """Пересоздаёт тестовую базу с нуля: каждый прогон проверяет миграции на чистой БД."""
    db_url = make_url(url)
    admin = db_url.set(drivername="postgresql", database="postgres")
    with psycopg.connect(
        admin.render_as_string(hide_password=False), autocommit=True
    ) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{db_url.database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{db_url.database}"')


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    _recreate_database(TEST_DATABASE_URL)
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    yield


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    # Тест целиком в одной транзакции, в конце откат; commit() сервисов становится savepoint'ом
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        yield session
        await session.close()
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def sources() -> Sources:
    """Источники — код симулятора в том же процессе, без сети и без пауз между повторами."""
    return build_sources(ASGITransport(app=simulator_app), backoff=0)


@pytest.fixture
async def client(
    db_session: AsyncSession, sources: Sources
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_async_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_async_session
    app.dependency_overrides[get_sources] = lambda: sources
    limiter.enabled = (
        False  # лимиты общие на процесс — тесты быстро упираются в 3/минуту
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    limiter.enabled = True


async def _register_and_login(client: AsyncClient, email: str, n: int) -> str:
    await client.post("/auth/register", json=registration_payload(email, n))
    response = await client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    return response.json()["access_token"]


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    token = await _register_and_login(client, "user@example.com", 1)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_auth_headers(client: AsyncClient) -> dict[str, str]:
    token = await _register_and_login(client, "other@example.com", 2)
    return {"Authorization": f"Bearer {token}"}
