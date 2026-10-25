"""Результаты конвейера: балл, вклад признаков, стоп-факторы, решение по заявке."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CreditDecision,
    FeatureDefinition,
    ScoreFeatureValue,
    ScoreResult,
    StopFactor,
    StopFactorResult,
)


async def ensure_stop_factors(session: AsyncSession, rows: list[dict]) -> None:
    """Справочник стоп-факторов: новые добавляет, у существующих обновляет описание."""
    stmt = insert(StopFactor).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["code"],
        set_={
            "name": stmt.excluded.name,
            "severity": stmt.excluded.severity,
            "rule_expression": stmt.excluded.rule_expression,
        },
    )
    await session.execute(stmt)


async def known_features(session: AsyncSession, codes: list[str]) -> set[str]:
    stmt = select(FeatureDefinition.code).where(FeatureDefinition.code.in_(codes))
    return set((await session.execute(stmt)).scalars())


async def add_score_result(
    session: AsyncSession,
    result: ScoreResult,
    values: list[ScoreFeatureValue],
    stops: list[StopFactorResult],
) -> ScoreResult:
    session.add(result)
    await session.flush()
    for row in (*values, *stops):
        row.score_result_id = result.id
    session.add_all([*values, *stops])
    await session.flush()
    return result


async def add_decision(session: AsyncSession, decision: CreditDecision) -> None:
    session.add(decision)
    await session.flush()


async def latest_decision(
    session: AsyncSession, application_id: uuid.UUID
) -> tuple[CreditDecision, ScoreResult | None] | None:
    stmt = (
        select(CreditDecision, ScoreResult)
        .outerjoin(ScoreResult, ScoreResult.id == CreditDecision.score_result_id)
        .where(CreditDecision.application_id == application_id)
        .order_by(CreditDecision.decided_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    return (row[0], row[1]) if row else None


async def score_points(session: AsyncSession, score_id: uuid.UUID) -> dict[str, float]:
    """Баллы каждого признака в расчёте: код признака → баллы."""
    stmt = select(ScoreFeatureValue.feature_code, ScoreFeatureValue.points).where(
        ScoreFeatureValue.score_result_id == score_id
    )
    return {f: float(p or 0) for f, p in (await session.execute(stmt)).all()}
