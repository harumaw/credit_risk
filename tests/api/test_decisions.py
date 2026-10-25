"""Конвейер решения: отправка → воркер → решение → выбор варианта → подписание → выдача."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_sources
from app.integrations.registry import Sources, build_sources
from app.main import app
from app.models import (
    CreditDecision,
    LoanApplication,
    ScoreResult,
    StopFactorResult,
    Task,
)
from app.seed import (
    DEMO_PASSWORD,
    seed_demo_users,
    seed_products,
    seed_stop_factors,
)
from app.settings import settings
from app.worker import run_once
from simulator.main import app as simulator_app

SEVERNY = "7701234560"  # высокая нагрузка → контрпредложение
IGOR_IP = "770700000190"  # идеальный ИП → одобрение
ANNA_IP = "500100000015"  # счёт в другом банке → ручной разбор (нет оборотов)
NEW_START = "7801002002"  # 4 месяца → мягкий отказ
VECTOR = "5403004007"  # просрочка 45 дней в прошлом → ручной разбор
ZAKAT = "6605006009"  # банкротство → жёсткий отказ
MAX_TASKS = 20  # воркер в тесте не крутится бесконечно, даже если код сломан
STREAM_TIMEOUT = 30

pytestmark = pytest.mark.usefixtures("scoring_models")


@pytest.fixture(autouse=True)
async def reference_data(db_session: AsyncSession) -> None:
    await seed_products(db_session)
    await seed_stop_factors(db_session)
    await seed_demo_users(db_session)


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _company(client: AsyncClient, headers: dict[str, str], inn: str) -> str:
    response = await client.post("/companies", json={"inn": inn}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _submit(
    client: AsyncClient,
    headers: dict[str, str],
    company_id: str,
    amount: int = 5_000_000,
    term: int = 12,
    key: str | None = None,
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
    extra = {"Idempotency-Key": key} if key else {}
    response = await client.post("/applications", json=form, headers=headers | extra)
    assert response.status_code == 201, response.text
    return response.json()


async def _drain(session: AsyncSession, sources: Sources) -> None:
    for _ in range(MAX_TASKS):
        if not await run_once(session, sources):
            return
    pytest.fail("очередь не опустела за MAX_TASKS задач")


async def _decided(
    client: AsyncClient,
    session: AsyncSession,
    sources: Sources,
    email: str,
    inn: str,
    amount: int = 5_000_000,
    term: int = 12,
) -> tuple[dict[str, str], dict]:
    headers = await _login(client, email)
    company_id = await _company(client, headers, inn)
    application = await _submit(client, headers, company_id, amount, term)
    await _drain(session, sources)
    response = await client.get(f"/applications/{application['id']}", headers=headers)
    assert response.status_code == 200
    return headers, response.json()


async def _stored(session: AsyncSession, application_id: str) -> CreditDecision:
    decision = await session.scalar(
        select(CreditDecision).where(CreditDecision.application_id == application_id)
    )
    assert decision is not None
    return decision


async def test_submit_queues_task(client: AsyncClient, db_session: AsyncSession):
    headers = await _login(client, "igor@example.com")
    application = await _submit(
        client, headers, await _company(client, headers, IGOR_IP)
    )

    assert application["status"] == "submitted" and application["decision"] is None
    tasks = await db_session.execute(
        select(Task.kind, Task.status).where(Task.application_id == application["id"])
    )
    assert tasks.all() == [("process_application", "queued")]


# --- Персоны CLAUDE.md §9: сегмент, грейд, исход ----------------------------


async def test_ideal_ip_is_approved(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    _, app_ = await _decided(
        client, db_session, sources, "igor@example.com", IGOR_IP, 1_000_000, 12
    )

    d = app_["decision"]
    assert app_["status"] == "approved" and d["outcome"] == "approved"
    assert d["grade"] == "A" and d["score"] is not None
    assert [(o["amount"], o["termMonths"]) for o in d["offers"]] == [(1_000_000, 12)]
    assert (d["amount"], d["termMonths"], d["rate"]) == (1_000_000, 12, 24.0)
    assert d["monthlyPayment"] == d["offers"][0]["monthlyPayment"] > 0
    assert d["alternatives"] == [] and d["acceptedOfferIndex"] is None
    assert [e["status"] for e in app_["history"]] == [
        "submitted",
        "checking",
        "approved",
    ]

    # состав: модель, сегмент, входы, балл, PD, грейд, стоп-факторы
    stored = await _stored(db_session, app_["id"])
    model = stored.details["model"]
    assert model["segment"] == "new_business"  # кредитов в КИ нет
    assert model["name"] == "msb_new_business" and model["version"]
    assert stored.details["inputs"]["features"]["bki_loans_cnt"] == 0
    score = await db_session.get(ScoreResult, stored.score_result_id)
    assert score is not None and score.grade == "A" and score.pd is not None
    assert score.input_sha256 and not score.has_hard_stop
    stops = await db_session.scalar(
        select(func.count())
        .select_from(StopFactorResult)
        .where(StopFactorResult.score_result_id == score.id)
    )
    assert stops == 8  # каждый фактор справочника с результатом


async def test_high_load_gets_two_offers(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    _, app_ = await _decided(
        client, db_session, sources, "anna@example.com", SEVERNY, 5_000_000, 12
    )

    d = app_["decision"]
    assert app_["status"] == "counter_offer" and d["outcome"] == "counter_offer"
    assert d["grade"] == "B"
    first, second = d["offers"]
    # CLAUDE.md §10: доход 450 тыс, платежи 100 тыс, 12 мес → ≈ 2,75 млн (ставка B = 25%)
    assert first["termMonths"] == 12 and 2_700_000 <= first["amount"] <= 2_749_000
    assert second["termMonths"] > 12 and second["amount"] == 5_000_000
    assert (d["amount"], d["termMonths"]) == (first["amount"], 12)
    assert d["reasons"][0]["code"] == "ABOVE_LIMIT" and d["hints"]
    assert d["alternatives"] == []  # альтернативы — только при отказе
    stored = await _stored(db_session, app_["id"])
    assert stored.details["model"]["segment"] == "sme"
    assert stored.details["inputs"]["dscr"] == pytest.approx(4.5, abs=0.01)


async def test_bankrupt_is_declined_by_stop_factor_without_scoring(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    _, app_ = await _decided(client, db_session, sources, "sergey@example.com", ZAKAT)

    d = app_["decision"]
    assert app_["status"] == "rejected" and d["outcome"] == "declined"
    assert {r["code"] for r in d["reasons"]} == {"COMPANY_INACTIVE", "BANKRUPTCY"}
    assert d["grade"] is None and d["score"] is None
    assert d["offers"] == [] and d["alternatives"] == [] and d["hints"]
    scores = await db_session.scalar(
        select(func.count())
        .select_from(ScoreResult)
        .where(ScoreResult.application_id == app_["id"])
    )
    assert scores == 0
    stored = await _stored(db_session, app_["id"])
    assert stored.details["model"] is None
    triggered = {
        s["code"] for s in stored.details["inputs"]["stopFactors"] if s["triggered"]
    }
    assert {"COMPANY_INACTIVE", "BANKRUPTCY"} <= triggered


async def test_young_business_is_softly_declined_with_date(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    _, app_ = await _decided(
        client, db_session, sources, "olga@example.com", NEW_START, 500_000, 12
    )

    d = app_["decision"]
    assert d["outcome"] == "declined" and d["grade"] is not None  # балл посчитан
    assert [r["code"] for r in d["reasons"]] == ["AGE_LT_6M"]
    assert d["hints"][0].startswith("Подайте заявку после ")
    stored = await _stored(db_session, app_["id"])
    assert stored.details["model"]["segment"] == "new_business"


async def test_past_delinquency_goes_to_manual_review(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    _, app_ = await _decided(client, db_session, sources, "dmitry@example.com", VECTOR)

    d = app_["decision"]
    assert app_["status"] == "checking" and d["outcome"] == "manual_review"
    assert [r["code"] for r in d["reasons"]] == ["PAST_DPD_30"]
    assert d["grade"] is not None and d["hints"]
    assert app_["history"][-1]["label"] == "На рассмотрении у специалиста"
    stored = await _stored(db_session, app_["id"])
    features = stored.details["inputs"]["features"]
    assert features["bki_months_since_dpd"] < 99  # просрочка видна в строке КИ
    assert stored.details["model"]["segment"] == "sme"


async def test_no_turnovers_goes_to_manual_review(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    _, app_ = await _decided(
        client, db_session, sources, "anna@example.com", ANNA_IP, 500_000, 12
    )

    d = app_["decision"]
    assert d["outcome"] == "manual_review"
    assert [r["code"] for r in d["reasons"]] == ["NO_STATEMENT"]
    assert "выписку" in d["hints"][0]


# --- Действия клиента -------------------------------------------------------


async def test_choose_second_offer_sign_and_issue(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, app_ = await _decided(
        client, db_session, sources, "anna@example.com", SEVERNY, 5_000_000, 12
    )
    base = f"/applications/{app_['id']}"
    second = app_["decision"]["offers"][1]

    early = await client.post(f"{base}/sign-code", headers=headers)
    assert early.status_code == 409  # условия ещё не приняты
    bad_index = await client.post(
        f"{base}/accept", json={"offerIndex": 5}, headers=headers
    )
    assert bad_index.status_code == 422

    accepted = await client.post(
        f"{base}/accept", json={"offerIndex": 1}, headers=headers
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["status"] == "signing"
    d = body["decision"]
    assert d["acceptedOfferIndex"] == 1
    assert (d["amount"], d["termMonths"], d["monthlyPayment"]) == (
        second["amount"],
        second["termMonths"],
        second["monthlyPayment"],
    )
    assert (await client.post(f"{base}/accept", headers=headers)).status_code == 409

    code = (await client.post(f"{base}/sign-code", headers=headers)).json()["code"]
    wrong = "000000" if code != "000000" else "111111"
    bad = await client.post(f"{base}/sign", json={"code": wrong}, headers=headers)
    assert bad.status_code == 422

    signed = await client.post(f"{base}/sign", json={"code": code}, headers=headers)
    assert signed.status_code == 200, signed.text
    body = signed.json()
    assert body["status"] == "issued"
    assert [e["label"] for e in body["history"]][-3:] == [
        "Подписание",
        "Договор подписан",
        "Кредит выдан",
    ]
    again = await client.post(f"{base}/sign", json={"code": code}, headers=headers)
    assert again.status_code == 409
    assert (await client.post(f"{base}/cancel", headers=headers)).status_code == 409


async def test_accept_without_body_takes_first_offer(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, app_ = await _decided(
        client, db_session, sources, "igor@example.com", IGOR_IP, 1_000_000, 12
    )
    response = await client.post(f"/applications/{app_['id']}/accept", headers=headers)
    assert response.status_code == 200
    assert response.json()["decision"]["acceptedOfferIndex"] == 0


async def test_expired_offer_cannot_be_accepted(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, app_ = await _decided(
        client, db_session, sources, "igor@example.com", IGOR_IP, 1_000_000, 12
    )
    decision = await _stored(db_session, app_["id"])
    decision.offer_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.flush()

    response = await client.post(f"/applications/{app_['id']}/accept", headers=headers)
    assert response.status_code == 409
    assert "истёк" in response.json()["detail"]


async def _signing(
    client: AsyncClient, session: AsyncSession, sources: Sources
) -> tuple[dict[str, str], str]:
    headers, app_ = await _decided(
        client, session, sources, "igor@example.com", IGOR_IP, 1_000_000, 12
    )
    base = f"/applications/{app_['id']}"
    assert (await client.post(f"{base}/accept", headers=headers)).status_code == 200
    return headers, base


async def test_expired_sign_code_is_rejected(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, base = await _signing(client, db_session, sources)
    code = (await client.post(f"{base}/sign-code", headers=headers)).json()["code"]
    application = await db_session.get(LoanApplication, base.rsplit("/", 1)[1])
    assert application is not None
    application.sign_code_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()

    late = await client.post(f"{base}/sign", json={"code": code}, headers=headers)
    assert late.status_code == 422
    assert "устарел" in late.json()["detail"][0]["msg"]

    code = (await client.post(f"{base}/sign-code", headers=headers)).json()["code"]
    signed = await client.post(f"{base}/sign", json={"code": code}, headers=headers)
    assert signed.status_code == 200, signed.text


async def test_sign_code_burns_after_five_wrong_attempts(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, base = await _signing(client, db_session, sources)
    code = (await client.post(f"{base}/sign-code", headers=headers)).json()["code"]
    wrong = "000000" if code != "000000" else "111111"
    messages = []
    for _ in range(5):
        bad = await client.post(f"{base}/sign", json={"code": wrong}, headers=headers)
        assert bad.status_code == 422
        messages.append(bad.json()["detail"][0]["msg"])
    assert messages[:4] == ["Неверный код"] * 4
    assert "запросите новый" in messages[4]

    # верный, но уже сгоревший код не проходит — только новый
    burnt = await client.post(f"{base}/sign", json={"code": code}, headers=headers)
    assert burnt.status_code == 422
    code = (await client.post(f"{base}/sign-code", headers=headers)).json()["code"]
    bad = await client.post(f"{base}/sign", json={"code": wrong}, headers=headers)
    assert bad.json()["detail"][0]["msg"] == "Неверный код"  # счётчик сброшен
    signed = await client.post(f"{base}/sign", json={"code": code}, headers=headers)
    assert signed.status_code == 200, signed.text


async def test_client_can_refuse_at_signing(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, base = await _signing(client, db_session, sources)

    refused = await client.post(f"{base}/cancel", headers=headers)

    assert refused.status_code == 200, refused.text
    body = refused.json()
    assert body["status"] == "cancelled"
    assert body["history"][-1]["label"] == "Заявка отменена"
    # подписать отменённую заявку уже нельзя, отменить повторно — тоже
    assert (await client.post(f"{base}/sign-code", headers=headers)).status_code == 409
    assert (await client.post(f"{base}/cancel", headers=headers)).status_code == 409


async def test_decline_cannot_be_accepted(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, app_ = await _decided(
        client, db_session, sources, "sergey@example.com", ZAKAT
    )
    response = await client.post(f"/applications/{app_['id']}/accept", headers=headers)
    assert response.status_code == 409


async def test_cancel_before_processing_skips_decision(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers = await _login(client, "igor@example.com")
    application = await _submit(
        client, headers, await _company(client, headers, IGOR_IP)
    )
    cancelled = await client.post(
        f"/applications/{application['id']}/cancel", headers=headers
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"

    await _drain(db_session, sources)

    body = (
        await client.get(f"/applications/{application['id']}", headers=headers)
    ).json()
    assert body["decision"] is None
    assert [e["status"] for e in body["history"]] == ["submitted", "cancelled"]


async def test_idempotent_submit(client: AsyncClient, db_session: AsyncSession):
    headers = await _login(client, "igor@example.com")
    company_id = await _company(client, headers, IGOR_IP)

    first = await _submit(client, headers, company_id, key="form-1")
    second = await _submit(client, headers, company_id, key="form-1")
    third = await _submit(client, headers, company_id, key="form-2")

    assert first["id"] == second["id"] != third["id"]
    tasks = await db_session.scalar(select(func.count()).select_from(Task))
    assert tasks == 2


async def test_foreign_application_actions_are_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
    sources: Sources,
    other_auth_headers: dict[str, str],
):
    _, app_ = await _decided(
        client, db_session, sources, "igor@example.com", IGOR_IP, 1_000_000, 12
    )
    base = f"/applications/{app_['id']}"
    for path in ("/accept", "/cancel", "/sign-code"):
        response = await client.post(base + path, headers=other_auth_headers)
        assert response.status_code == 404
    events = await client.get(f"{base}/events", headers=other_auth_headers)
    assert events.status_code == 404


# --- SSE --------------------------------------------------------------------


def _events(text: str) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.fixture
def fast_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EVENTS_POLL_SECONDS", 0.01)
    monkeypatch.setattr(settings, "EVENTS_MAX_SECONDS", 0.2)


@pytest.mark.usefixtures("fast_events")
async def test_events_stream_closes_after_final_status(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, app_ = await _decided(
        client, db_session, sources, "sergey@example.com", ZAKAT
    )

    response = await asyncio.wait_for(
        client.get(f"/applications/{app_['id']}/events", headers=headers),
        STREAM_TIMEOUT,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [e["status"] for e in _events(response.text)] == [
        "submitted",
        "checking",
        "rejected",
    ]


@pytest.mark.usefixtures("fast_events")
async def test_events_stream_has_time_limit_before_final_status(
    client: AsyncClient, db_session: AsyncSession, sources: Sources
):
    headers, app_ = await _decided(
        client, db_session, sources, "dmitry@example.com", VECTOR
    )  # ручной разбор — не финальный статус

    response = await asyncio.wait_for(
        client.get(f"/applications/{app_['id']}/events", headers=headers),
        STREAM_TIMEOUT,
    )

    assert [e["status"] for e in _events(response.text)][-1] == "checking"


# --- Отказоустойчивость -----------------------------------------------------


class _BrokenBki(httpx.AsyncBaseTransport):
    def __init__(self):
        self.inner = ASGITransport(app=simulator_app)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/bki/"):
            return httpx.Response(503)
        return await self.inner.handle_async_request(request)


async def test_source_outage_goes_to_manual_review(
    client: AsyncClient, db_session: AsyncSession
):
    broken = build_sources(_BrokenBki(), retries=1, backoff=0)
    app.dependency_overrides[get_sources] = lambda: broken
    _, app_ = await _decided(
        client, db_session, broken, "igor@example.com", IGOR_IP, 1_000_000, 12
    )

    d = app_["decision"]
    assert d["outcome"] == "manual_review"
    assert [r["code"] for r in d["reasons"]] == ["SOURCE_ERROR"]


async def test_crashing_task_is_retried_then_sent_to_review(
    client: AsyncClient,
    db_session: AsyncSession,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
):
    async def crash(*args, **kwargs):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr("app.services.pipeline.score_company", crash)
    monkeypatch.setattr(settings, "WORKER_RETRY_SECONDS", 0)
    _, app_ = await _decided(
        client, db_session, sources, "igor@example.com", IGOR_IP, 1_000_000, 12
    )

    task = await db_session.scalar(
        select(Task).where(Task.application_id == app_["id"])
    )
    assert task is not None and task.status == "failed"
    assert task.attempts == settings.WORKER_MAX_ATTEMPTS
    assert app_["decision"]["outcome"] == "manual_review"
    assert [e["status"] for e in app_["history"]] == [
        "submitted",
        "checking",
        "checking",
    ]
