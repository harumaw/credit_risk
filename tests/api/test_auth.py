from httpx import AsyncClient


async def test_register_login_me(client: AsyncClient, auth_headers: dict[str, str]):
    response = await client.get("/auth/me", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["status"] == "pending_verification"


async def test_duplicate_email_rejected(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "password123"}
    assert (await client.post("/auth/register", json=payload)).status_code == 201
    assert (await client.post("/auth/register", json=payload)).status_code == 400


async def test_wrong_password_rejected(client: AsyncClient):
    await client.post(
        "/auth/register", json={"email": "a@example.com", "password": "password123"}
    )
    response = await client.post(
        "/auth/login", json={"email": "a@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_garbage_token_rejected(client: AsyncClient):
    response = await client.get(
        "/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401
