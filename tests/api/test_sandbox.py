"""Песочница: любой новый пользователь добавляет тестовую компанию и получает решение."""

import re
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.registry import Sources
from app.sandbox import SANDBOX_INNS
from app.seed import DEMO_USERS, seed_demo_users, seed_products, seed_stop_factors
from simulator.sandbox import DEFAULT_DIRECTOR, SANDBOX
from tests.api.test_decisions import _drain, _submit
from tests.helpers import registration_payload

pytestmark = pytest.mark.usefixtures("scoring_models")


@pytest.fixture(autouse=True)
async def reference_data(db_session: AsyncSession) -> None:
    await seed_products(db_session)
    await seed_stop_factors(db_session)


async def _new_user(client: AsyncClient, n: int) -> dict[str, str]:
    payload = registration_payload(f"tester{n}@example.com", 100 + n)
    assert (await client.post("/auth/register", json=payload)).status_code == 201
    response = await client.post(
        "/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _add(client: AsyncClient, headers: dict[str, str], inn: str) -> str:
    lookup = await client.post("/companies/lookup", json={"inn": inn}, headers=headers)
    assert lookup.json()["directorMatches"] is True, lookup.text
    response = await client.post("/companies", json={"inn": inn}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_app_and_simulator_agree_on_sandbox_inns():
    assert set(SANDBOX) == SANDBOX_INNS


@pytest.mark.parametrize(
    ("inn", "amount", "outcome", "reason"),
    [
        ("9900000017", 1_000_000, "approved", None),
        ("9900000024", 5_000_000, "counter_offer", "ABOVE_LIMIT"),
        ("9900000031", 500_000, "declined", "AGE_LT_6M"),
        ("9900000049", 3_000_000, "manual_review", "PAST_DPD_30"),
        ("9900000056", 5_000_000, "declined", "COMPANY_INACTIVE"),
        ("9900000063", 500_000, "manual_review", "NO_STATEMENT"),
    ],
)
async def test_fresh_user_gets_scenario_outcome(
    client: AsyncClient,
    db_session: AsyncSession,
    sources: Sources,
    inn: str,
    amount: int,
    outcome: str,
    reason: str | None,
):
    headers = await _new_user(client, 1)
    company_id = await _add(client, headers, inn)
    application = await _submit(client, headers, company_id, amount, 12)
    await _drain(db_session, sources)

    body = (
        await client.get(f"/applications/{application['id']}", headers=headers)
    ).json()
    d = body["decision"]
    assert body["companyName"].startswith("ООО «Тест — ")
    assert d["outcome"] == outcome
    if reason:
        assert d["reasons"][0]["code"] == reason and d["hints"]


async def test_two_testers_share_company_but_not_applications(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    first, second = await _new_user(client, 1), await _new_user(client, 2)
    company_a = await _add(client, first, "9900000017")
    company_b = await _add(client, second, "9900000017")
    assert company_a == company_b  # компания одна, связь у каждого своя

    mine = await _submit(client, first, company_a, 1_000_000, 12)
    theirs = await _submit(client, second, company_b, 1_000_000, 12)
    await _drain(db_session, sources)

    for headers, own, other in ((first, mine, theirs), (second, theirs, mine)):
        listed = (await client.get("/applications", headers=headers)).json()
        assert [a["id"] for a in listed] == [own["id"]]
        base = f"/applications/{other['id']}"
        assert (await client.get(base, headers=headers)).status_code == 404
        assert (await client.get(f"{base}/events", headers=headers)).status_code == 404
        for action in ("/accept", "/cancel", "/sign-code"):
            response = await client.post(base + action, headers=headers)
            assert response.status_code == 404


async def test_regular_company_still_needs_real_director(
    client: AsyncClient, db_session: AsyncSession
):
    headers = await _new_user(client, 1)
    lookup = await client.post(
        "/companies/lookup", json={"inn": "7701234560"}, headers=headers
    )
    assert lookup.json()["directorMatches"] is False
    response = await client.post(
        "/companies", json={"inn": "7701234560"}, headers=headers
    )
    assert response.status_code == 403


def _readme_inns() -> list[str]:
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(
        encoding="utf-8"
    )
    block = readme.split("<!-- registration-inns -->")[1].split("<!--")[0]
    return re.findall(r"`(\d{12})`", block)


async def test_readme_registration_inns_are_valid_and_free(
    client: AsyncClient, db_session: AsyncSession
):
    inns = _readme_inns()
    assert len(inns) == len(set(inns)) == 10
    taken = {u.inn_fl for u in DEMO_USERS} | {DEFAULT_DIRECTOR[1]}
    assert not taken & set(inns)
    await seed_demo_users(db_session)
    for n, inn in enumerate(inns):
        payload = registration_payload(f"reader{n}@example.com", 1, inn_fl=inn)
        response = await client.post("/auth/register", json=payload)
        assert response.status_code == 201, (inn, response.text)
