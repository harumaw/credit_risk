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
from tests.helpers import registration_payload

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
    assert body["kind"] == "ul"
    assert body["registeredAt"] == "апрель 2019"
    assert body["activity"].startswith("46.90 · ")
    assert body["director"] == "Смирнова Анна Викторовна"
    assert body["directorMatches"] is True
    assert body["alreadyAddedId"] is None


async def test_foreign_company_cannot_be_added(
    client: AsyncClient, anna: dict[str, str]
):
    lookup = await client.post("/companies/lookup", json={"inn": FOREIGN}, headers=anna)
    assert lookup.json()["directorMatches"] is False

    response = await client.post("/companies", json={"inn": FOREIGN}, headers=anna)
    assert response.status_code == 403
    assert "другой человек" in response.json()["detail"]
    assert (await client.get("/companies", headers=anna)).json() == []


async def test_namesake_of_director_cannot_add_company(client: AsyncClient):
    """ФИО совпадает с руководителем, ИНН ФЛ — другой: компания не его."""
    payload = registration_payload(
        "namesake@example.com",
        3,
        last_name="Смирнова",
        first_name="Анна",
        middle_name="Викторовна",
    )
    assert (await client.post("/auth/register", json=payload)).status_code == 201
    login = await client.post(
        "/auth/login",
        json={"email": "namesake@example.com", "password": payload["password"]},
    )
    namesake = {"Authorization": f"Bearer {login.json()['access_token']}"}

    lookup = await client.post(
        "/companies/lookup", json={"inn": SEVERNY}, headers=namesake
    )
    assert lookup.json()["directorMatches"] is False

    response = await client.post("/companies", json={"inn": SEVERNY}, headers=namesake)
    assert response.status_code == 403


async def test_add_company_collects_every_source(
    client: AsyncClient, anna: dict[str, str], db_session: AsyncSession
):
    body = await _add(client, anna, SEVERNY)

    assert body["hasStatement"] is True and body["isBankClient"] is True
    assert "checks" not in body  # в ответе — короткая карточка
    company_id = body["id"]

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

    sources = (
        await client.get(f"/companies/{company_id}/sources", headers=anna)
    ).json()
    keys = ["egrul", "fns", "rmsp", "fssp", "efrsb", "zsk", "bki", "turnover"]
    assert [s["key"] for s in sources] == keys
    assert {s["state"] for s in sources} == {"done"}


async def test_add_same_company_twice_conflicts(
    client: AsyncClient, anna: dict[str, str]
):
    await _add(client, anna, SEVERNY)
    response = await client.post("/companies", json={"inn": SEVERNY}, headers=anna)
    assert response.status_code == 409

    lookup = await client.post("/companies/lookup", json={"inn": SEVERNY}, headers=anna)
    assert lookup.json()["alreadyAddedId"] is not None


async def test_company_details(client: AsyncClient, anna: dict[str, str]):
    company_id = (await _add(client, anna, SEVERNY))["id"]

    response = await client.get(f"/companies/{company_id}", headers=anna)

    assert response.status_code == 200
    c = response.json()
    assert c["category"] == "small" and c["employees"] == 24
    assert (c["taxRegime"], c["taxRegimeNote"]) == ("УСН", "«доходы»")
    assert c["registeredYear"] == 2019
    assert len(c["flows"]) == 24 and len(c["forecast"]) == 3
    assert len(c["inflowTrend"]) == 12
    assert c["flows"][-1]["inflow"]["our"] == c["inflowTrend"][-1]
    assert c["monthlyPayment"] == 100_000  # 68 400 + 31 600
    assert c["debt"] == 2_100_000 and c["loansCount"] == 2
    assert c["dscr"] == pytest.approx(4.5, abs=0.01)
    # CLAUDE.md §10: доход 450 тыс, платежи 100 тыс, 12 мес, 24% → ≈ 2,75 млн
    assert 2_740_000 <= c["limit"] <= 2_750_000
    assert c["nextPayment"]["amount"] in (68_400, 31_600)
    assert sorted(loan["balance"] for loan in c["loans"]) == [860_000, 1_240_000]
    assert c["checksOk"] == c["checksTotal"] == len(c["checks"]) == 6
    assert c["okved"][0] == {
        "code": "46.90",
        "title": "Торговля оптовая неспециализированная",
        "main": True,
    }


async def test_ip_without_statement_has_no_limit(
    client: AsyncClient, anna: dict[str, str]
):
    company = await _add(client, anna, ANNA_IP)
    assert company["kind"] == "ip" and company["name"] == "ИП Смирнова А. В."
    assert company["hasStatement"] is False
    assert company["limit"] is None and company["limitNote"]
    assert company["taxRegime"] == "Патент"
    assert company["inflowTrend"] == []

    sources = (
        await client.get(f"/companies/{company['id']}/sources", headers=anna)
    ).json()
    states = {s["key"]: s["state"] for s in sources}
    assert states["turnover"] == "error" and states["egrul"] == "done"
    assert sources[0]["label"] == "ЕГРИП"


async def test_group_summary(client: AsyncClient, anna: dict[str, str]):
    await _add(client, anna, SEVERNY)
    await _add(client, anna, ANNA_IP)

    response = await client.get("/companies/group-summary", headers=anna)

    assert response.status_code == 200
    g = response.json()
    assert g["debt"] == 2_100_000
    assert g["monthlyPayments"] == 100_000
    assert g["loansCount"] == 2
    assert g["companiesWithoutStatement"] == 1
    assert len(g["inflowTrend"]) == 12 and g["lastMonth"]
    assert g["checksOk"] == g["checksTotal"] == 12
    # доход ИП не известен — лимит по одной компании, с пометкой про выписку
    assert 2_740_000 <= g["limit"] <= 2_750_000
    assert "ИП Смирнова А. В." in g["limitNote"]


async def test_empty_cabinet(client: AsyncClient, anna: dict[str, str]):
    assert (await client.get("/companies", headers=anna)).json() == []
    g = (await client.get("/companies/group-summary", headers=anna)).json()
    assert g["limit"] is None and g["inflowTrend"] == [] and g["nextPayment"] is None


async def test_bankrupt_company_is_added_without_limit(
    client: AsyncClient, db_session: AsyncSession
):
    await seed_demo_users(db_session)
    sergey = await _login(client, "sergey@example.com")
    company_id = (await _add(client, sergey, ZAKAT))["id"]

    c = (await client.get(f"/companies/{company_id}", headers=sergey)).json()

    assert c["limit"] is None and "банкротство" in c["limitNote"]
    failed = {ch["label"] for ch in c["checks"] if not ch["ok"]}
    expected = {"Статус в ЕГРЮЛ", "Налоговый долг", "ФССП", "Банкротства"}
    assert expected | {"Зона риска ЦБ"} <= failed


async def test_foreign_company_is_not_found(
    client: AsyncClient, anna: dict[str, str], other_auth_headers: dict[str, str]
):
    company_id = (await _add(client, anna, SEVERNY))["id"]

    for path in (f"/companies/{company_id}", f"/companies/{company_id}/sources"):
        response = await client.get(path, headers=other_auth_headers)
        assert response.status_code == 404


async def test_other_user_does_not_see_foreign_companies(
    client: AsyncClient, anna: dict[str, str], other_auth_headers: dict[str, str]
):
    await _add(client, anna, SEVERNY)

    assert (await client.get("/companies", headers=other_auth_headers)).json() == []
    g = (
        await client.get("/companies/group-summary", headers=other_auth_headers)
    ).json()
    assert g["limit"] is None and g["loansCount"] == 0 and g["debt"] == 0


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
    client: AsyncClient, anna: dict[str, str], db_session: AsyncSession
):
    transport = _FailingBki()
    app.dependency_overrides[get_sources] = lambda: build_sources(
        transport, retries=2, backoff=0
    )

    company = await _add(client, anna, SEVERNY)

    assert transport.bki_calls == 3  # первая попытка + 2 повтора
    sources = (
        await client.get(f"/companies/{company['id']}/sources", headers=anna)
    ).json()
    states = {s["key"]: s["state"] for s in sources}
    assert states["bki"] == "error" and states["turnover"] == "done"
    error = await db_session.execute(
        select(DataFetch.error).where(DataFetch.status == "error")
    )
    assert "HTTP 500" in error.scalar_one()


async def test_seed_is_idempotent(db_session: AsyncSession):
    assert await seed_demo_users(db_session) == 5
    assert await seed_demo_users(db_session) == 0
