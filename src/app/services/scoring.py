"""Выбор модели для компании и расчёт балла: сегмент → champion сегмента → скоркарта.

Порядок: активные сегменты по priority, первый подошедший по условиям; если у него нет
модели-champion — запасной сегмент `all`. Стоп-факторы проверяются до вызова (конвейер).
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.credit.scorecard import ScoreOutcome, match_segment, score
from app.models import ModelVersion
from app.repositories import scoring as scoring_repo

FALLBACK_SEGMENT = "all"


class NoScoringModel(Exception):
    """В БД нет ни одной рабочей модели (не загружены: python -m app.dataload.synthetic)."""


@dataclass(frozen=True)
class ModelChoice:
    segment_code: str
    model: ModelVersion


async def choose_model(session: AsyncSession, features: dict[str, Any]) -> ModelChoice:
    segments = await scoring_repo.active_segments(session)
    code = match_segment(segments, features)
    for candidate in (code, FALLBACK_SEGMENT):
        if candidate is None:
            continue
        model = await scoring_repo.champion(session, candidate)
        if model is not None:
            return ModelChoice(candidate, model)
    raise NoScoringModel("нет модели-champion ни для сегмента, ни для запасного 'all'")


async def score_company(
    session: AsyncSession, features: dict[str, Any]
) -> tuple[ModelChoice, ScoreOutcome]:
    choice = await choose_model(session, features)
    card = await scoring_repo.load_scorecard(session, choice.model)
    return choice, score(card, features)
