"""Скоринг компании вне заявки — для кабинета администратора и загрузки синтетики.

Синтетика — признаки из обучающей выборки на её дату; клиент кабинета — те же данные и тот же
расчёт, что в конвейере (`pipeline.gather` → `company_features`, `stop_factors.evaluate`),
на сегодня, без нового запроса к источникам. Решение — рекомендация по матрице без DSCR
(`credit/recommendation.py`).
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.credit.features import company_features
from app.credit.recommendation import (
    hard_codes,
    hard_stops,
    recommend,
    recommend_checks,
)
from app.credit.scorecard import match_segment, score
from app.credit.stop_factors import StopCheck, evaluate
from app.models import Company, ScoreFeatureValue, ScoreResult, StopFactorResult
from app.repositories import scoring as scoring_repo
from app.services.pipeline import gather
from app.services.scoring import choose_model


@dataclass(frozen=True)
class CompanyInput:
    """Вход скоринга: признаки на дату, откуда они и проверенные стоп-факторы."""

    as_of: date
    features: dict[str, Any]
    source: str  # synthetic / live
    checks: list[StopCheck] = field(default_factory=list)


async def company_input(session: AsyncSession, company: Company) -> CompanyInput:
    sample = await scoring_repo.dataset_sample(session, company.id)
    if sample is not None:
        status = company.status.value if company.status else "active"
        features = dict(sample.features)
        codes = hard_stops({**features, "company_status": status})
        checks = [StopCheck(code, True, {}) for code in codes]
        return CompanyInput(sample.as_of_date, features, "synthetic", checks)
    today = datetime.now(UTC).date()
    data = await gather(session, company, today)
    return CompanyInput(
        today, company_features(data.facts), "live", evaluate(data.stop)
    )


def _sha256(features: dict[str, Any]) -> str:
    raw = json.dumps(features, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


async def score_and_save(session: AsyncSession, company: Company) -> ScoreResult:
    """Скоринг champion-моделью сегмента: вход, вклады признаков, стоп-факторы, рекомендация."""
    started = time.monotonic()
    data = await company_input(session, company)
    triggered = [c.code for c in data.checks if c.triggered]
    segments = await scoring_repo.active_segments(session)
    segment_code = match_segment(segments, data.features)
    choice = await choose_model(session, data.features)
    card = await scoring_repo.load_scorecard(session, choice.model)
    outcome = score(card, data.features)
    bins = await scoring_repo.bin_ids(session, choice.model.id)
    hard = bool(hard_codes(triggered))
    result = ScoreResult(
        id=uuid.uuid4(),
        company_id=company.id,
        model_version_id=choice.model.id,
        as_of_date=data.as_of,
        total_score=Decimal(str(outcome.score)),
        pd=Decimal(str(outcome.pd)),
        grade=outcome.grade,
        has_hard_stop=hard,
        input_sha256=_sha256(data.features),
        segment_code=segment_code,
        features=data.features,
        reason_codes=outcome.reason_codes(),
        recommended_decision=(
            recommend_checks(outcome.grade, triggered)
            if data.source == "live"
            else recommend(outcome.grade, hard)
        ),
    )
    result.latency_ms = int((time.monotonic() - started) * 1000)
    session.add(result)
    await session.flush()
    for c in outcome.contributions:
        numeric = isinstance(c.value, int | float) and not isinstance(c.value, bool)
        session.add(
            ScoreFeatureValue(
                score_result_id=result.id,
                feature_code=c.feature,
                value_num=Decimal(str(c.value)) if numeric else None,
                value_text=None if numeric or c.value is None else str(c.value),
                bin_id=bins.get((c.feature, c.bin_order)),
                points=Decimal(str(c.points)),
            )
        )
    for check in data.checks:
        session.add(
            StopFactorResult(
                score_result_id=result.id,
                stop_factor_code=check.code,
                triggered=check.triggered,
                details=check.details or None,
            )
        )
    await session.flush()
    return result
