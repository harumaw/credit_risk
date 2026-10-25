"""Кабинет администратора: вход сотрудника, изоляция токенов, компании, модели, срезы."""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import DataSource, DefaultTrigger, ModelStatus
from app.models import (
    Company,
    DefaultEvent,
    FeatureDefinition,
    MlDatasetSample,
    ModelVersion,
    RatingScale,
    ScorecardBin,
    ScoreResult,
    ScoringSegment,
    StaffUser,
)
from app.seed import seed_admin
from app.services.rescoring import score_and_save
from app.settings import settings

ADMIN_PASSWORD = "test-admin-pass-1"


@pytest.fixture
async def admin_headers(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
) -> dict[str, str]:
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", ADMIN_PASSWORD)
    await seed_admin(db_session)
    response = await client.post(
        "/admin/auth/login",
        json={"login": settings.ADMIN_LOGIN, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["staff"]["role"] == "admin"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _model(name: str, status: ModelStatus, young_points: float) -> list:
    model = ModelVersion(
        id=uuid.uuid4(),
        model_name=name,
        version="t",
        model_type="scorecard",
        segment_code="all",
        status=status,
        target_definition="test",
        params={"intercept_points": 500, "pd_a": 10.0, "pd_b": -0.02},
    )
    return [
        model,
        ScorecardBin(id=uuid.uuid4(), model_version_id=model.id, feature_code="company_age_months",
                     bin_order=0, upper_bound=12, woe=-0.5, points=young_points, event_rate=0.2),
        ScorecardBin(id=uuid.uuid4(), model_version_id=model.id, feature_code="company_age_months",
                     bin_order=1, lower_bound=12, woe=0.4, points=10, event_rate=0.02),
        RatingScale(model_version_id=model.id, grade="A", score_from=505, score_to=9999, pd_calibrated=0.01),
        RatingScale(model_version_id=model.id, grade="E", score_from=-9999, score_to=505, pd_calibrated=0.2),
    ]  # fmt: skip


@pytest.fixture
async def scored(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    """Две синтетические компании: зрелая (одобрение, но был дефолт) и молодая (отказ)."""
    db_session.add_all(
        [
            ScoringSegment(code="all", name="все", priority=100, is_active=True, conditions={}),
            FeatureDefinition(code="company_age_months", name="Возраст бизнеса", data_type="numeric",
                              source=DataSource.FNS_EGRUL),
        ]
    )  # fmt: skip
    await db_session.flush()
    # champion отказывает молодым, challenger — нет: на молодой компании решения расходятся
    db_session.add_all(_model("t_champion", ModelStatus.CHAMPION, -10))
    db_session.add_all(_model("t_challenger", ModelStatus.CHALLENGER, 6))
    await db_session.flush()

    ids = {}
    for key, inn, age in (("old", "7700000001", 40), ("young", "7700000002", 3)):
        company = Company(
            id=uuid.uuid4(), inn=inn, full_name=f"ООО «Тест {key}»", legal_form="ООО"
        )
        db_session.add(company)
        await db_session.flush()
        db_session.add(
            MlDatasetSample(
                dataset_code="t_ds",
                company_id=company.id,
                as_of_date=date(2025, 3, 1),
                sample="oot",
                target=1 if key == "old" else 0,
                features={"company_age_months": age, "legal_form": "ЮЛ"},
            )
        )
        if key == "old":
            db_session.add(
                DefaultEvent(
                    company_id=company.id,
                    trigger=DefaultTrigger.DPD_90,
                    default_date=date(2025, 9, 1),
                )
            )
        await db_session.flush()
        await score_and_save(db_session, company)
        ids[key] = company.id
    await db_session.flush()
    return ids


# ------------------------------------------------------------------ вход


async def test_admin_login_rejects_wrong_password(
    client: AsyncClient, admin_headers: dict[str, str]
):
    response = await client.post(
        "/admin/auth/login", json={"login": settings.ADMIN_LOGIN, "password": "nope"}
    )
    assert response.status_code == 401


async def test_staff_and_client_tokens_are_isolated(
    client: AsyncClient, admin_headers: dict[str, str], auth_headers: dict[str, str]
):
    assert (await client.get("/admin/me", headers=admin_headers)).status_code == 200
    # клиентский токен в админке не работает, токен сотрудника — в кабинете клиента
    assert (await client.get("/admin/me", headers=auth_headers)).status_code == 401
    assert (await client.get("/auth/me", headers=admin_headers)).status_code == 401
    assert (await client.get("/admin/summary")).status_code == 401


async def test_seed_admin_needs_password(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", None)
    message = await seed_admin(db_session)
    assert "не задан" in message
    staff = await db_session.execute(
        select(StaffUser).where(StaffUser.login == settings.ADMIN_LOGIN)
    )
    assert staff.scalar_one_or_none() is None


# ------------------------------------------------------------------ компании


async def test_companies_list_filters_and_random(
    client: AsyncClient, admin_headers: dict[str, str], scored: dict[str, uuid.UUID]
):
    response = await client.get("/admin/companies", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2

    # «пропуск модели»: одобрили, а был дефолт
    missed = await client.get(
        "/admin/companies",
        params={"decision": "approve", "fact": "default"},
        headers=admin_headers,
    )
    items = missed.json()["items"]
    assert [i["id"] for i in items] == [str(scored["old"])]
    assert items[0]["grade"] == "A" and items[0]["source"] == "synthetic"

    first = await client.get(
        "/admin/companies", params={"random": "true", "seed": 42}, headers=admin_headers
    )
    again = await client.get(
        "/admin/companies", params={"random": "true", "seed": 42}, headers=admin_headers
    )
    assert first.json()["seed"] == 42
    assert [i["id"] for i in first.json()["items"]] == [
        i["id"] for i in again.json()["items"]
    ]

    csv = await client.get(
        "/admin/companies.csv", params={"decision": "decline"}, headers=admin_headers
    )
    assert csv.status_code == 200
    lines = csv.text.strip().splitlines()
    assert len(lines) == 2 and "7700000002" in lines[1]

    assert (
        await client.get(
            "/admin/companies", params={"sort": "bad"}, headers=admin_headers
        )
    ).status_code == 422


async def test_company_card_shows_score_breakdown(
    client: AsyncClient, admin_headers: dict[str, str], scored: dict[str, uuid.UUID]
):
    response = await client.get(
        f"/admin/companies/{scored['young']}", headers=admin_headers
    )
    assert response.status_code == 200
    card = response.json()
    assert card["fact"] == {
        "known": True,
        "default": False,
        "defaultDate": None,
        "trigger": None,
    }
    score = card["score"]
    assert score["model"] == "t_champion" and score["score"] == 490
    assert score["decision"] == "decline" and score["nextGradeAt"] == 505
    [contribution] = score["contributions"]
    assert contribution["feature"] == "company_age_months"
    assert contribution["lost"] == 20
    # challenger на тех же входах одобрил бы
    challenger = next(a for a in card["alternatives"] if a["model"] == "t_challenger")
    assert challenger["score"] == 506 and challenger["grade"] == "A"

    missing = await client.get(
        f"/admin/companies/{uuid.uuid4()}", headers=admin_headers
    )
    assert missing.status_code == 404


async def test_rescore_adds_history(
    client: AsyncClient,
    admin_headers: dict[str, str],
    scored: dict[str, uuid.UUID],
    db_session: AsyncSession,
):
    response = await client.post(
        f"/admin/companies/{scored['old']}/score", headers=admin_headers
    )
    assert response.status_code == 200
    rows = await db_session.execute(
        select(ScoreResult).where(ScoreResult.company_id == scored["old"])
    )
    assert len(rows.scalars().all()) == 2
    card = (
        await client.get(f"/admin/companies/{scored['old']}", headers=admin_headers)
    ).json()
    assert len(card["history"]) == 2


# ------------------------------------------------------------------ модели и срезы


async def test_model_detail_and_calculator(
    client: AsyncClient, admin_headers: dict[str, str], scored: dict[str, uuid.UUID]
):
    models = (await client.get("/admin/models", headers=admin_headers)).json()
    champion = next(m for m in models["models"] if m["name"] == "t_champion")
    assert [s["code"] for s in models["segments"]] == ["all"]

    detail = (
        await client.get(f"/admin/models/{champion['id']}", headers=admin_headers)
    ).json()
    [feature] = detail["features"]
    assert [b["label"] for b in feature["bins"]] == ["< 12", "≥ 12"]
    assert {g["grade"] for g in detail["grades"]} == {"A", "E"}

    calc = await client.post(
        f"/admin/models/{champion['id']}/calculate",
        json={"features": {"company_age_months": 50}},
        headers=admin_headers,
    )
    assert calc.status_code == 200
    assert calc.json()["score"] == 510 and calc.json()["grade"] == "A"

    example = await client.get(
        "/admin/example", params={"decision": "decline"}, headers=admin_headers
    )
    assert example.json()["companyId"] == str(scored["young"])


async def test_analysis_matrix_and_disagreement(
    client: AsyncClient, admin_headers: dict[str, str], scored: dict[str, uuid.UUID]
):
    cells = (await client.get("/admin/analysis/matrix", headers=admin_headers)).json()[
        "cells"
    ]
    counts = {(c["decision"], c["fact"]): c["count"] for c in cells}
    assert counts == {("approve", "default"): 1, ("decline", "no_default"): 1}

    data = (
        await client.get(
            "/admin/analysis/disagreement",
            params={"sample": 10, "seed": 1},
            headers=admin_headers,
        )
    ).json()
    assert data["sample"] == 2
    by_model = {m["model"]: m for m in data["models"]}
    assert by_model["t_champion"]["agreeShare"] == 1
    assert by_model["t_challenger"]["agreeShare"] == 0.5
    assert [e["id"] for e in data["examples"]] == [str(scored["young"])]

    monthly = (
        await client.get("/admin/analysis/monthly", headers=admin_headers)
    ).json()["months"]
    assert monthly == [
        {
            "month": "2025-03",
            "n": 2,
            "approveShare": 0.5,
            "avgPd": monthly[0]["avgPd"],
            "defaultRate": 0.5,
            "avgScore": 500.0,
        }
    ]
