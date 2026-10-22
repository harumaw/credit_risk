import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApplicationStatusHistory, Consent, LoanApplication
from app.seed import DEMO_PASSWORD, seed_demo_users, seed_products

SEVERNY = "7701234560"  # ООО «Северный ветер», руководитель — Анна


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def anna(client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    await seed_products(db_session)
    await seed_demo_users(db_session)
    return await _login(client, "anna@example.com")


@pytest.fixture
async def severny(client: AsyncClient, anna: dict[str, str]) -> str:
    response = await client.post("/companies", json={"inn": SEVERNY}, headers=anna)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _form(company_id: str, **overrides: object) -> dict[str, object]:
    form: dict[str, object] = {
        "companyId": company_id,
        "productCode": "WORKING_CAPITAL",
        "amount": 5_000_000,
        "termMonths": 12,
        "purpose": "Пополнение оборотных средств",
        "consentPersonalData": True,
        "consentBki": True,
    }
    form.update(overrides)
    return form


async def test_products_are_active_only(client: AsyncClient, anna: dict[str, str]):
    response = await client.get("/applications/products", headers=anna)

    assert response.status_code == 200
    codes = [p["code"] for p in response.json()]
    assert codes == ["WORKING_CAPITAL", "CREDIT_LINE", "OVERDRAFT"]  # залог скрыт
    working = response.json()[0]
    assert working["minAmount"] == 300_000
    assert working["maxTermMonths"] == 60
    assert working["rate"] == 24.0


async def test_submit_saves_application(
    client: AsyncClient, anna: dict[str, str], severny: str, db_session: AsyncSession
):
    response = await client.post("/applications", json=_form(severny), headers=anna)

    assert response.status_code == 201, response.text
    body = response.json()
    assert int(body["number"]) >= 1001  # из sequence: откат теста номер не возвращает
    assert body["companyName"] == "ООО «Северный ветер»"
    assert body["product"] == "Кредит на оборотные средства"
    assert (body["amount"], body["termMonths"]) == (5_000_000, 12)
    assert body["status"] == "submitted"
    assert [e["status"] for e in body["history"]] == ["submitted"]

    saved = await db_session.get(LoanApplication, body["id"])
    assert saved is not None and saved.submitted_at is not None
    consents = await db_session.scalar(
        select(func.count())
        .select_from(Consent)
        .where(Consent.application_id == saved.id)
    )
    assert consents == 2
    events = await db_session.scalar(
        select(func.count())
        .select_from(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == saved.id)
    )
    assert events == 1


async def test_list_and_details(
    client: AsyncClient, anna: dict[str, str], severny: str
):
    first = (
        await client.post("/applications", json=_form(severny), headers=anna)
    ).json()
    second = (
        await client.post(
            "/applications",
            json=_form(severny, productCode="CREDIT_LINE", amount=1_000_000),
            headers=anna,
        )
    ).json()
    assert int(second["number"]) == int(first["number"]) + 1

    listed = (await client.get("/applications", headers=anna)).json()
    assert [a["id"] for a in listed] == [second["id"], first["id"]]  # новые выше

    details = await client.get(f"/applications/{first['id']}", headers=anna)
    assert details.status_code == 200
    assert details.json()["purpose"] == "Пополнение оборотных средств"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"amount": 100_000}, "amount"),  # меньше минимума продукта
        ({"amount": 60_000_000}, "amount"),
        ({"termMonths": 72}, "termMonths"),
        ({"productCode": "SECURED"}, "productCode"),  # продукт скрыт
        ({"consentBki": False}, "consentBki"),
        ({"purpose": " "}, "purpose"),
    ],
)
async def test_invalid_form_rejected(
    client: AsyncClient,
    anna: dict[str, str],
    severny: str,
    overrides: dict[str, object],
    field: str,
):
    response = await client.post(
        "/applications", json=_form(severny, **overrides), headers=anna
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == field
    assert (await client.get("/applications", headers=anna)).json() == []


async def test_cannot_apply_for_foreign_company(
    client: AsyncClient,
    anna: dict[str, str],
    severny: str,
    other_auth_headers: dict[str, str],
):
    response = await client.post(
        "/applications", json=_form(severny), headers=other_auth_headers
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "companyId"


async def test_foreign_application_is_hidden(
    client: AsyncClient,
    anna: dict[str, str],
    severny: str,
    other_auth_headers: dict[str, str],
):
    created = (
        await client.post("/applications", json=_form(severny), headers=anna)
    ).json()

    assert (await client.get("/applications", headers=other_auth_headers)).json() == []
    hidden = await client.get(
        f"/applications/{created['id']}", headers=other_auth_headers
    )
    assert hidden.status_code == 404


async def test_requires_auth(client: AsyncClient):
    assert (await client.get("/applications")).status_code == 401
