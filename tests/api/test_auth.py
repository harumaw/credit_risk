from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import UserStatus
from app.models import User
from tests.helpers import make_inn_fl, registration_payload


async def test_register_returns_profile(client: AsyncClient):
    payload = registration_payload(
        "new@example.com", middle_name="  Петрович ", phone="8 (900) 123-45-67"
    )
    response = await client.post("/auth/register", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["last_name"] == "Иванов"
    assert body["middle_name"] == "Петрович"
    assert body["inn_fl"] == make_inn_fl(1)
    assert body["phone"] == "+79001234567"
    assert body["status"] == "active"
    assert "password" not in body and "password_hash" not in body


async def test_register_login_me(client: AsyncClient, auth_headers: dict[str, str]):
    response = await client.get("/auth/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


async def test_empty_optional_fields_become_null(client: AsyncClient):
    payload = registration_payload("opt@example.com", middle_name="", phone="  ")
    body = (await client.post("/auth/register", json=payload)).json()

    assert body["middle_name"] is None
    assert body["phone"] is None


async def test_required_fields(client: AsyncClient):
    for field in ("last_name", "first_name", "inn_fl"):
        payload = registration_payload("req@example.com")
        del payload[field]
        response = await client.post("/auth/register", json=payload)
        assert response.status_code == 422, field

    blank_name = registration_payload("req@example.com", first_name="   ")
    assert (await client.post("/auth/register", json=blank_name)).status_code == 422


async def test_invalid_inn_rejected(client: AsyncClient):
    good = make_inn_fl(1)
    broken_checksum = good[:-1] + str((int(good[-1]) + 1) % 10)
    for inn in (broken_checksum, "12345", "7707083893"):  # последний — ИНН юрлица
        payload = registration_payload("inn@example.com", inn_fl=inn)
        assert (await client.post("/auth/register", json=payload)).status_code == 422, (
            inn
        )


async def test_invalid_phone_rejected(client: AsyncClient):
    payload = registration_payload("ph@example.com", phone="12345")
    assert (await client.post("/auth/register", json=payload)).status_code == 422


async def test_duplicates_rejected(client: AsyncClient):
    first = registration_payload("dup@example.com", 1, phone="+79001234567")
    assert (await client.post("/auth/register", json=first)).status_code == 201

    cases = {
        "email": registration_payload("dup@example.com", 2),
        "ИНН": registration_payload("other@example.com", 1),
        "телефоном": registration_payload("third@example.com", 3, phone="89001234567"),
    }
    for word, payload in cases.items():
        response = await client.post("/auth/register", json=payload)
        assert response.status_code == 400
        assert word in response.json()["detail"]


async def test_wrong_password_rejected(client: AsyncClient):
    await client.post("/auth/register", json=registration_payload("a@example.com"))
    response = await client.post(
        "/auth/login", json={"email": "a@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_blocked_user_cannot_login(client: AsyncClient, db_session: AsyncSession):
    await client.post("/auth/register", json=registration_payload("b@example.com"))
    await db_session.execute(
        update(User)
        .where(User.email == "b@example.com")
        .values(status=UserStatus.BLOCKED)
    )
    await db_session.commit()

    response = await client.post(
        "/auth/login", json={"email": "b@example.com", "password": "password123"}
    )
    assert response.status_code == 403


async def test_garbage_token_rejected(client: AsyncClient):
    response = await client.get(
        "/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401
