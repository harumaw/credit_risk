"""Одновременная отправка заявок — на отдельных соединениях и с настоящими коммитами.

Общая фикстура `client` держит тест в одной транзакции, гонку там не увидеть: здесь у каждого
запроса своя сессия. Всё, что тест закоммитил, в конце удаляется.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.dependencies import get_async_session
from app.enums import CompanyRole, LinkStatus
from app.main import app
from app.models import Company, UserCompanyLink
from app.rate_limit import limiter
from app.seed import seed_products
from tests.conftest import TEST_DATABASE_URL, sync_dsn
from tests.helpers import registration_payload

RACE_INN = "9900000999"  # только для этого теста, в симуляторе нет — источники не нужны
EMAIL = "race@example.com"


def _cleanup() -> None:
    with psycopg.connect(sync_dsn()) as conn, conn.cursor() as cur:
        apps = (
            "SELECT a.id FROM loan_applications a JOIN users u"
            " ON u.id = a.applicant_user_id WHERE u.email = %(email)s"
        )
        for table in ("tasks", "application_status_history"):
            cur.execute(
                f"DELETE FROM {table} WHERE application_id IN ({apps})",
                {"email": EMAIL},
            )
        users = "SELECT id FROM users WHERE email = %(email)s"
        for table, column in (
            ("consents", "user_id"),
            ("loan_applications", "applicant_user_id"),
            ("user_company_links", "user_id"),
        ):
            cur.execute(
                f"DELETE FROM {table} WHERE {column} IN ({users})", {"email": EMAIL}
            )
        cur.execute("DELETE FROM companies WHERE inn = %s", (RACE_INN,))
        cur.execute("DELETE FROM users WHERE email = %s", (EMAIL,))
        conn.commit()


@pytest.fixture
async def race() -> AsyncGenerator[tuple[AsyncClient, dict[str, str], str], None]:
    """Клиент, у которого каждый запрос — своя сессия и своё соединение; автор и компания."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def own_session() -> AsyncGenerator[AsyncSession, None]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_async_session] = own_session
    limiter.enabled = False
    _cleanup()
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = registration_payload(EMAIL, 900)
            assert (
                await client.post("/auth/register", json=payload)
            ).status_code == 201
            token = (
                await client.post(
                    "/auth/login",
                    json={"email": EMAIL, "password": payload["password"]},
                )
            ).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            me = (await client.get("/auth/me", headers=headers)).json()
            async with sessions() as session:
                await seed_products(session)
                company = Company(inn=RACE_INN, full_name="ООО «Гонка»")
                session.add(company)
                await session.flush()
                session.add(
                    UserCompanyLink(
                        user_id=uuid.UUID(me["id"]),
                        company_id=company.id,
                        role=CompanyRole.DIRECTOR,
                        status=LinkStatus.CONFIRMED,
                    )
                )
                await session.commit()
            yield client, headers, str(company.id)
    finally:
        app.dependency_overrides.clear()
        limiter.enabled = True
        _cleanup()
        await engine.dispose()


def _form(company_id: str) -> dict[str, object]:
    return {
        "companyId": company_id,
        "productCode": "WORKING_CAPITAL",
        "amount": 1_000_000,
        "termMonths": 12,
        "purpose": "Пополнение оборотных средств",
        "consentPersonalData": True,
        "consentBki": True,
    }


async def test_simultaneous_submits_get_distinct_numbers(race):
    client, headers, company_id = race
    responses = await asyncio.gather(
        *(
            client.post(
                "/applications",
                json=_form(company_id),
                headers={**headers, "Idempotency-Key": f"race-{n}"},
            )
            for n in range(5)
        )
    )
    assert [r.status_code for r in responses] == [201] * 5, [
        r.text[:200] for r in responses
    ]
    assert len({r.json()["number"] for r in responses}) == 5


async def test_simultaneous_retry_with_same_key_returns_same_application(race):
    client, headers, company_id = race
    retry = {**headers, "Idempotency-Key": "double-click"}
    responses = await asyncio.gather(
        *(
            client.post("/applications", json=_form(company_id), headers=retry)
            for _ in range(2)
        )
    )
    assert [r.status_code for r in responses] == [201, 201], [
        r.text[:200] for r in responses
    ]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    listed = (await client.get("/applications", headers=headers)).json()
    assert len(listed) == 1
