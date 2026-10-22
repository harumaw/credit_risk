"""Паритет: признаки и балл конвейера (таблицы БД → CompanyFacts → company_features) совпадают
с обучающей выборкой (ml_dataset_samples.features ← ml/build_features.py) на тех же компаниях.

Ловит главный риск адаптера: балл считается, но не тот, на котором училась модель.
"""

from collections.abc import Iterator

import psycopg
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.credit.features import company_features
from app.dataload.synthetic import delete_previous, load_data
from app.models import Company, MlDatasetSample
from app.services.pipeline import gather
from app.services.scoring import score_company
from tests.conftest import SYNTHETIC, sync_dsn

SAMPLE_SIZE = 40
pytestmark = pytest.mark.usefixtures("scoring_models")


@pytest.fixture(scope="module")
def synthetic_companies(scoring_models) -> Iterator[None]:
    with psycopg.connect(sync_dsn()) as conn, conn.cursor() as cur:
        load_data(cur, SYNTHETIC, limit=SAMPLE_SIZE)
        conn.commit()
    yield
    with psycopg.connect(sync_dsn()) as conn, conn.cursor() as cur:
        delete_previous(cur, "synthetic_v1")
        conn.commit()


def _same(a, b) -> bool:
    if isinstance(a, int | float) and isinstance(b, int | float):
        return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))
    return a == b


@pytest.mark.usefixtures("synthetic_companies")
async def test_pipeline_features_and_score_match_training(db_session: AsyncSession):
    samples = (
        await db_session.execute(
            select(MlDatasetSample, Company).join(
                Company, Company.id == MlDatasetSample.company_id
            )
        )
    ).all()
    assert len(samples) == SAMPLE_SIZE

    mismatches = []
    segments = set()
    for sample, company in samples:
        data = await gather(db_session, company, sample.as_of_date)
        ours = company_features(data.facts)
        trained = sample.features
        for name, expected in trained.items():
            if not _same(ours.get(name), expected):
                mismatches.append((company.inn, name, ours.get(name), expected))
        choice, outcome = await score_company(db_session, ours)
        ref_choice, ref = await score_company(db_session, trained)
        assert choice.segment_code == ref_choice.segment_code, company.inn
        assert outcome.score == pytest.approx(ref.score, abs=1e-6), company.inn
        assert outcome.grade == ref.grade
        segments.add(choice.segment_code)

    assert mismatches == []
    assert len(segments) >= 2  # выборка задела больше одного сегмента
