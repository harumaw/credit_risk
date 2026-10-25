"""Наши кредиты входят в долговую нагрузку: максимум нельзя взять дважды или по частям."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.registry import Sources
from app.models import Loan
from app.seed import (
    DEMO_PASSWORD,
    seed_demo_users,
    seed_products,
    seed_stop_factors,
)
from app.worker import run_once

IGOR_IP = "770700000190"  # идеальный ИП, без кредитов в КИ
SEVERNY = "7701234560"  # ООО с кредитами в КИ
PROBE = 50_000_000  # больше любого лимита — решение покажет максимум
MAX_TASKS = 20

pytestmark = pytest.mark.usefixtures("scoring_models")


@pytest.fixture(autouse=True)
async def reference_data(db_session: AsyncSession) -> None:
    await seed_products(db_session)
    await seed_stop_factors(db_session)
    await seed_demo_users(db_session)


async def _start(client: AsyncClient, email: str, inn: str):
    login = await client.post(
        "/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    company = await client.post("/companies", json={"inn": inn}, headers=headers)
    assert company.status_code == 201, company.text
    return headers, company.json()["id"]


async def _apply(
    client: AsyncClient,
    session: AsyncSession,
    sources: Sources,
    headers: dict,
    company_id: str,
    amount: int,
    term: int = 12,
) -> dict:
    form = {
        "companyId": company_id,
        "productCode": "WORKING_CAPITAL",
        "amount": amount,
        "termMonths": term,
        "purpose": "Пополнение оборотных средств",
        "consentPersonalData": True,
        "consentBki": True,
    }
    submitted = await client.post("/applications", json=form, headers=headers)
    assert submitted.status_code == 201, submitted.text
    for _ in range(MAX_TASKS):
        if not await run_once(session, sources):
            break
    response = await client.get(
        f"/applications/{submitted.json()['id']}", headers=headers
    )
    return response.json()


async def _max_amount(client, session, sources, headers, company_id) -> int:
    """Максимум на 12 мес — первый вариант контрпредложения на заведомо большую сумму."""
    probe = await _apply(client, session, sources, headers, company_id, PROBE)
    assert probe["decision"]["outcome"] == "counter_offer"
    await client.post(f"/applications/{probe['id']}/cancel", headers=headers)
    return probe["decision"]["offers"][0]["amount"]


async def _issue(client: AsyncClient, headers: dict, application: dict) -> None:
    base = f"/applications/{application['id']}"
    accepted = await client.post(f"{base}/accept", headers=headers)
    assert accepted.status_code == 200, accepted.text
    code = (await client.post(f"{base}/sign-code", headers=headers)).json()["code"]
    signed = await client.post(f"{base}/sign", json={"code": code}, headers=headers)
    assert signed.json()["status"] == "issued"


@pytest.mark.parametrize(
    "email,inn", [("igor@example.com", IGOR_IP), ("anna@example.com", SEVERNY)]
)
async def test_maximum_cannot_be_taken_twice(
    client: AsyncClient, db_session: AsyncSession, sources: Sources, email, inn
):
    headers, company_id = await _start(client, email, inn)
    limit = await _max_amount(client, db_session, sources, headers, company_id)
    first = await _apply(client, db_session, sources, headers, company_id, limit)
    assert first["decision"]["outcome"] == "approved"
    await _issue(client, headers, first)

    loan = await db_session.scalar(
        select(Loan).where(Loan.application_id == first["id"])
    )
    assert loan is not None and loan.amount == limit and loan.term_months == 12

    card = (await client.get(f"/companies/{company_id}", headers=headers)).json()
    assert card["limit"] < 1_000  # максимум выбран — свободного лимита нет
    assert any(row["balance"] == limit for row in card["loans"])  # наш кредит в списке

    again = await _apply(client, db_session, sources, headers, company_id, limit)
    assert again["decision"]["outcome"] == "declined"
    assert [r["code"] for r in again["decision"]["reasons"]] == ["DSCR_LOW"]
    probe = await _apply(client, db_session, sources, headers, company_id, PROBE)
    assert probe["decision"]["offers"] == []  # и больше на длинный срок — тоже нет


async def test_small_loans_do_not_add_up_above_maximum(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, company_id = await _start(client, "igor@example.com", IGOR_IP)
    limit = await _max_amount(client, db_session, sources, headers, company_id)
    part = limit // 3 // 1000 * 1000
    issued = []
    for _ in range(6):  # просим треть максимума, пока дают; берём то, что предложили
        small = await _apply(client, db_session, sources, headers, company_id, part)
        if not small["decision"]["offers"]:
            break
        await _issue(client, headers, small)
        issued.append(small["decision"]["offers"][0]["amount"])
    assert len(issued) >= 2  # маленькие кредиты дают, пока есть запас по доходу
    assert sum(issued) <= limit  # но в сумме не больше, чем один большой
    last = await _apply(client, db_session, sources, headers, company_id, part)
    assert last["decision"]["outcome"] == "declined"


async def test_parallel_approvals_cannot_both_be_accepted(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, company_id = await _start(client, "igor@example.com", IGOR_IP)
    limit = await _max_amount(client, db_session, sources, headers, company_id)
    # две заявки на максимум решены до того, как клиент принял хоть одну
    first = await _apply(client, db_session, sources, headers, company_id, limit)
    second = await _apply(client, db_session, sources, headers, company_id, limit)
    assert first["decision"]["outcome"] == second["decision"]["outcome"] == "approved"

    ok = await client.post(f"/applications/{first['id']}/accept", headers=headers)
    assert ok.status_code == 200
    late = await client.post(f"/applications/{second['id']}/accept", headers=headers)
    assert late.status_code == 409
    assert "другой кредит" in late.json()["detail"]

    # клиент передумал и отменил первую — вторую снова можно принять
    await client.post(f"/applications/{first['id']}/cancel", headers=headers)
    retry = await client.post(f"/applications/{second['id']}/accept", headers=headers)
    assert retry.status_code == 200
