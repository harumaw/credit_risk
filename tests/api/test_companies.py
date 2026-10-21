import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_sources
from app.integrations.registry import build_sources
from app.main import app
from app.models import CreditObligation, DataFetch, MonthlyTurnover, UserCompanyLink
from app.seed import DEMO_PASSWORD, seed_demo_users
from simulator.main import app as simulator_app

SEVERNY = "7701234560"  # ООО «Северный ветер», руководитель — Анна
ANNA_IP = "500100000015"  # ИП Смирнова, счёт в другом банке
FOREIGN = "7709008002"  # сгенерированная компания с чужим руководителем
ZAKAT = "6605006009"  # банкротство, руководитель — Сергей


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def anna(client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    await seed_demo_users(db_session)
    return await _login(client, "anna@example.com")


async def _add(client: AsyncClient, headers: dict[str, str], inn: str) -> dict:
    response = await client.post("/companies", json={"inn": inn}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_lookup_own_company(client: AsyncClient, anna: dict[str, str]):
    response = await client.post(
        "/companies/lookup", json={"inn": SEVERNY}, headers=anna
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "ООО «Северный ветер»"
    assert body["director_name"] == "Смирнова Анна Викторовна"
    assert body["okved_main"]["code"] == "46.90"
    assert body["can_add"] is True and body["already_added"] is False


async def test_foreign_company_cannot_be_added(
    client: AsyncClient, anna: dict[str, str]
):
    lookup = await client.post("/companies/lookup", json={"inn": FOREIGN}, headers=anna)
    assert lookup.json()["can_add"] is False
    assert "другой человек" in lookup.json()["reason"]

    response = await client.post("/companies", json={"inn": FOREIGN}, headers=anna)
    assert response.status_code == 403
    assert (await client.get("/companies", headers=anna)).json() == []


async def test_add_company_collects_every_source(
    client: AsyncClient, anna: dict[str, str], db_session: AsyncSession
):
    body = await _add(client, anna, SEVERNY)

    assert body["company"]["needs_statement"] is False
    assert len(body["sources"]) == 8
    assert {s["status"] for s in body["sources"]} == {"success"}
    company_id = body["company"]["id"]

    async def count(model, column) -> int:
        stmt = select(func.count()).select_from(model).where(column == company_id)
        return (await db_session.execute(stmt)).scalar_one()

    assert await count(DataFetch, DataFetch.company_id) == 8  # снимок каждого ответа
    assert await count(CreditObligation, CreditObligation.company_id) == 2
    assert await count(UserCompanyLink, UserCompanyLink.company_id) == 1
    turnovers = await db_session.execute(
        select(func.count()).select_from(MonthlyTurnover)
    )
    assert turnovers.scalar_one() == 24


async def test_add_same_company_twice_conflicts(
    client: AsyncClient, anna: dict[str, str]
):
    await _add(client, anna, SEVERNY)
    response = await client.post("/companies", json={"inn": SEVERNY}, headers=anna)
    assert response.status_code == 409


async def test_company_summary(client: AsyncClient, anna: dict[str, str]):
    company_id = (await _add(client, anna, SEVERNY))["company"]["id"]

    response = await client.get(f"/companies/{company_id}/summary", headers=anna)

    assert response.status_code == 200
    s = response.json()
    assert s["company"]["is_bank_client"] is True
    assert len(s["turnovers"]) == 12 and len(s["forecast"]) == 3
    assert s["metrics"]["monthly_payments"] == 100_000  # 68 400 + 31 600
    assert s["metrics"]["monthly_income"] == pytest.approx(450_000, abs=5)
    assert s["metrics"]["inflow_12m_change_pct"] > 0
    # CLAUDE.md §10: доход 450 тыс, платежи 100 тыс, 12 мес, 24% → ≈ 2,75 млн
    assert 2_740_000 <= s["limit"]["amount"] <= 2_750_000
    assert s["limit"]["needs_statement"] is False
    assert sorted(loan["outstanding"] for loan in s["loans"]) == [860_000, 1_240_000]
    assert all(c["ok"] for c in s["checks"] if c["ok"] is not None)
    assert s["okved"][0]["code"] == "46.90"


async def test_ip_without_statement_has_no_limit(
    client: AsyncClient, anna: dict[str, str]
):
    body = await _add(client, anna, ANNA_IP)
    assert body["company"]["needs_statement"] is True
    assert body["company"]["kind"] == "ip"

    s = (
        await client.get(f"/companies/{body['company']['id']}/summary", headers=anna)
    ).json()
    assert s["limit"]["amount"] is None
    assert s["limit"]["needs_statement"] is True
    assert s["turnovers"] == [] and s["forecast"] == []


async def test_group_summary(client: AsyncClient, anna: dict[str, str]):
    await _add(client, anna, SEVERNY)
    await _add(client, anna, ANNA_IP)

    response = await client.get("/companies/group-summary", headers=anna)

    assert response.status_code == 200
    g = response.json()
    assert len(g["companies"]) == 2
    assert g["total_debt"] == 2_100_000
    assert g["monthly_payments"] == 100_000
    assert g["loans_count"] == 2
    assert g["next_payment"]["amount"] in (68_400, 31_600)
    # доход ИП не известен — лимит по одной компании, с пометкой про выписку
    assert 2_740_000 <= g["limit"]["amount"] <= 2_750_000
    assert g["limit"]["needs_statement"] is True
    assert "ИП Смирнова А. В." in g["limit"]["reason"]


async def test_bankrupt_company_is_added_without_limit(
    client: AsyncClient, db_session: AsyncSession
):
    await seed_demo_users(db_session)
    sergey = await _login(client, "sergey@example.com")
    company_id = (await _add(client, sergey, ZAKAT))["company"]["id"]

    s = (await client.get(f"/companies/{company_id}/summary", headers=sergey)).json()

    assert s["company"]["status"] == "bankrupt"
    assert s["limit"]["amount"] is None
    failed = {c["code"] for c in s["checks"] if c["ok"] is False}
    assert {"registry_status", "tax_debt", "fssp", "bankruptcy", "zsk"} <= failed


async def test_foreign_summary_is_not_found(
    client: AsyncClient, anna: dict[str, str], other_auth_headers: dict[str, str]
):
    company_id = (await _add(client, anna, SEVERNY))["company"]["id"]

    response = await client.get(
        f"/companies/{company_id}/summary", headers=other_auth_headers
    )
    assert response.status_code == 404


async def test_invalid_inn_rejected(client: AsyncClient, anna: dict[str, str]):
    response = await client.post(
        "/companies/lookup", json={"inn": "7701234567"}, headers=anna
    )
    assert response.status_code == 422


async def test_companies_require_auth(client: AsyncClient):
    assert (await client.get("/companies")).status_code == 401


class _FailingBki(httpx.AsyncBaseTransport):
    """БКИ всегда отвечает 500, остальные источники — как обычно."""

    def __init__(self):
        self.inner = ASGITransport(app=simulator_app)
        self.bki_calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/bki/"):
            self.bki_calls += 1
            return httpx.Response(500)
        return await self.inner.handle_async_request(request)


async def test_source_outage_is_recorded_and_retried(
    client: AsyncClient, anna: dict[str, str]
):
    transport = _FailingBki()
    app.dependency_overrides[get_sources] = lambda: build_sources(
        transport, retries=2, backoff=0
    )

    body = await _add(client, anna, SEVERNY)

    statuses = {s["source"]: s for s in body["sources"]}
    assert statuses["bki"]["status"] == "error"
    assert "HTTP 500" in statuses["bki"]["error"]
    assert transport.bki_calls == 3  # первая попытка + 2 повтора
    assert statuses["bank_internal"]["status"] == "success"


async def test_seed_is_idempotent(db_session: AsyncSession):
    assert await seed_demo_users(db_session) == 5
    assert await seed_demo_users(db_session) == 0
