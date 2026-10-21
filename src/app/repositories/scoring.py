"""Сегменты и модели скоринга из БД → объекты `app.credit.scorecard`."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.credit.scorecard import Bin, Grade, Scorecard, Segment
from app.enums import ModelStatus
from app.models import ModelVersion, RatingScale, ScorecardBin, ScoringSegment


async def active_segments(session: AsyncSession) -> list[Segment]:
    stmt = (
        select(ScoringSegment)
        .where(ScoringSegment.is_active.is_(True))
        .order_by(ScoringSegment.priority)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [Segment(s.code, s.priority, s.conditions, s.is_active) for s in rows]


async def champion(session: AsyncSession, segment_code: str) -> ModelVersion | None:
    stmt = (
        select(ModelVersion)
        .where(
            ModelVersion.segment_code == segment_code,
            ModelVersion.status == ModelStatus.CHAMPION,
        )
        .order_by(ModelVersion.created_at.desc())
    )
    return (await session.execute(stmt)).scalars().first()


async def load_scorecard(session: AsyncSession, model: ModelVersion) -> Scorecard:
    bins = (
        (
            await session.execute(
                select(ScorecardBin).where(ScorecardBin.model_version_id == model.id)
            )
        )
        .scalars()
        .all()
    )
    grades = (
        (
            await session.execute(
                select(RatingScale)
                .where(RatingScale.model_version_id == model.id)
                .order_by(RatingScale.score_from.desc())
            )
        )
        .scalars()
        .all()
    )
    params = model.params or {}
    return Scorecard(
        model_id=str(model.id),
        base_score=float(params.get("intercept_points", 0)),
        bins=[
            Bin(
                feature=b.feature_code,
                order=b.bin_order,
                points=float(b.points),
                woe=float(b.woe),
                lower=float(b.lower_bound) if b.lower_bound is not None else None,
                upper=float(b.upper_bound) if b.upper_bound is not None else None,
                categories=tuple(b.categories) if b.categories else None,
                is_missing=b.is_missing_bin,
            )
            for b in bins
        ],
        grades=[
            Grade(
                g.grade, float(g.score_from), float(g.score_to), float(g.pd_calibrated)
            )
            for g in grades
        ],
        pd_a=float(params.get("pd_a", 0.0)),
        pd_b=float(params.get("pd_b", 0.0)),
    )
