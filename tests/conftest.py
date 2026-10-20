import os

os.environ.setdefault("POSTGRES_DSN", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-tests-only")

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  — регистрирует все таблицы в Base.metadata
from app.database import Base
from app.dependencies import get_async_session
from app.main import app
from app.rate_limit import limiter
from tests.helpers import registration_payload

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_async_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_async_session
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
