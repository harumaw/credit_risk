"""Кабинет администратора на данных конвейера: заявка клиента → скоринг → разбор в /admin."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.registry import Sources
from app.seed import (
    DEMO_PASSWORD,
    seed_admin,
    seed_demo_users,
    seed_products,
    seed_stop_factors,
)
from app.settings import settings
from app.worker import run_once

IGOR_IP = "770700000190"  # идеальный ИП → одобрение моделью new_business
ADMIN_PASSWORD = "test-admin-pass-2"
MAX_TASKS = 20

pytestmark = pytest.mark.usefixtures("scoring_models")


@pytest.fixture
async def admin_headers(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> dict[str, str]:
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", ADMIN_PASSWORD)
    await seed_products(db_session)
    await seed_stop_factors(db_session)
    await seed_demo_users(db_session)
    await seed_admin(db_session)
    response = await client.post(
        "/admin/auth/login",
        json={"login": settings.ADMIN_LOGIN, "password": ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _approved_company(
    client: AsyncClient, session: AsyncSession, sources: Sources
) -> str:
    login = await client.post(
        "/auth/login", json={"email": "igor@example.com", "password": DEMO_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    company = await client.post("/companies", json={"inn": IGOR_IP}, headers=headers)
    company_id = company.json()["id"]
    submitted = await client.post(
        "/applications",
        json={
            "companyId": company_id,
            "productCode": "WORKING_CAPITAL",
            "amount": 1_000_000,
            "termMonths": 12,
            "purpose": "Пополнение оборотных средств",
            "consentPersonalData": True,
            "consentBki": True,
        },
        headers=headers,
    )
    assert submitted.status_code == 201, submitted.text
    for _ in range(MAX_TASKS):
        if not await run_once(session, sources):
            break
    return company_id


async def test_pipeline_score_is_visible_in_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    sources: Sources,
    admin_headers: dict[str, str],
):
    company_id = await _approved_company(client, db_session, sources)

    rows = await client.get(
        "/admin/companies", params={"source": "live"}, headers=admin_headers
    )
    [row] = [r for r in rows.json()["items"] if r["id"] == company_id]
    # итог заявки, сегмент и модель — из снимка, который конвейер пишет в score_results
    assert row["decision"] == "approve" and row["grade"] == "A"
    assert row["segment"] == "new_business" and row["model"] == "msb_new_business"

    card = (
        await client.get(f"/admin/companies/{company_id}", headers=admin_headers)
    ).json()
    score = card["score"]
    assert score["model"] == "msb_new_business" and score["contributions"]
    assert len(score["stops"]) == 8 and not any(s["triggered"] for s in score["stops"])
    assert card["features"]["bki_loans_cnt"] == 0

    # пересчёт на тех же данных источников — тот же балл, история растёт
    rescored = await client.post(
        f"/admin/companies/{company_id}/score", headers=admin_headers
    )
    assert rescored.status_code == 200
    card = (
        await client.get(f"/admin/companies/{company_id}", headers=admin_headers)
    ).json()
    assert len(card["history"]) == 2
    assert card["score"]["score"] == score["score"]
    assert card["score"]["decision"] == "approve"
