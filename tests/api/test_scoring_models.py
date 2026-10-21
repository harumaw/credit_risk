"""Модели и сегменты в БД: загрузка models.json и выбор модели для компании."""

import os
import uuid
from pathlib import Path

import psycopg
from sqlalchemy.ext.asyncio import AsyncSession

from app.dataload.synthetic import load_models
from app.enums import DataSource, ModelStatus
from app.models import (
    FeatureDefinition,
    ModelVersion,
    RatingScale,
    ScorecardBin,
    ScoringSegment,
)
from app.services.scoring import choose_model, score_company

MODELS_JSON = Path(__file__).resolve().parents[2] / "ml" / "artifacts" / "models.json"


def _sync_dsn() -> str:
    return os.environ["TEST_DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def test_models_json_loads_into_schema():
    # Загрузчик на реальной схеме; транзакция откатывается — app_test не меняется
    with psycopg.connect(_sync_dsn()) as conn, conn.cursor() as cur:
        load_models(cur, MODELS_JSON)
        cur.execute("SELECT count(*) FROM scoring_segments WHERE is_active")
        assert cur.fetchone()[0] >= 1
        cur.execute(
            "SELECT count(*) FROM model_versions WHERE segment_code = 'all' AND status = 'champion'"
        )
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT count(*) FROM scorecard_bins b JOIN model_versions m ON m.id = b.model_version_id"
        )
        assert cur.fetchone()[0] > 0
        load_models(cur, MODELS_JSON)  # повторная загрузка не дублирует модели
        cur.execute("SELECT count(*) FROM model_versions WHERE segment_code = 'all'")
        assert cur.fetchone()[0] == 1
        conn.rollback()


def _model(code: str, name: str, status: ModelStatus) -> ModelVersion:
    return ModelVersion(
        id=uuid.uuid4(),
        model_name=name,
        version="t",
        model_type="scorecard",
        segment_code=code,
        status=status,
        target_definition="test",
        params={"intercept_points": 500, "pd_a": 10.0, "pd_b": -0.02},
    )


async def test_choose_model_by_segment_and_fallback(db_session: AsyncSession):
    db_session.add_all(
        [
            ScoringSegment(code="t_young", name="молодые", priority=1, is_active=True,
                           conditions={"feature": "company_age_months", "op": "<", "value": 12}),
            ScoringSegment(code="t_nomodel", name="без модели", priority=2, is_active=True,
                           conditions={"feature": "legal_form", "op": "==", "value": "ИП"}),
            ScoringSegment(code="all", name="все", priority=100, is_active=True, conditions={}),
            FeatureDefinition(code="company_age_months", name="Возраст", data_type="numeric",
                              source=DataSource.FNS_EGRUL),
        ]
    )  # fmt: skip
    await db_session.flush()
    young = _model("t_young", "t_young_card", ModelStatus.CHAMPION)
    general = _model("all", "t_general", ModelStatus.CHAMPION)
    db_session.add_all(
        [young, general, _model("t_young", "t_young_old", ModelStatus.CHALLENGER)]
    )
    await db_session.flush()
    db_session.add_all(
        [
            ScorecardBin(id=uuid.uuid4(), model_version_id=young.id, feature_code="company_age_months",
                         bin_order=0, upper_bound=6, woe=-0.5, points=-10),
            ScorecardBin(id=uuid.uuid4(), model_version_id=young.id, feature_code="company_age_months",
                         bin_order=1, lower_bound=6, woe=0.2, points=8),
            RatingScale(model_version_id=young.id, grade="A", score_from=505, score_to=9999, pd_calibrated=0.01),
            RatingScale(model_version_id=young.id, grade="E", score_from=-9999, score_to=505, pd_calibrated=0.2),
        ]
    )  # fmt: skip
    await db_session.flush()

    choice = await choose_model(db_session, {"company_age_months": 3})
    assert (
        choice.segment_code == "t_young" and choice.model.model_name == "t_young_card"
    )
    # у сегмента нет champion → запасной `all`
    choice = await choose_model(
        db_session, {"company_age_months": 40, "legal_form": "ИП"}
    )
    assert choice.segment_code == "all" and choice.model.model_name == "t_general"

    choice, outcome = await score_company(db_session, {"company_age_months": 8})
    assert outcome.score == 508 and outcome.grade == "A"
