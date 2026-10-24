"""SQL кабинета администратора: сводка, список компаний с последним скорингом, разбор, срезы."""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import (
    DateTime,
    Select,
    Text,
    and_,
    case,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BankAccount,
    BankruptcyEvent,
    Company,
    CompanyOkved,
    CreditObligation,
    DataFetch,
    DefaultEvent,
    EnforcementProceeding,
    FeatureDefinition,
    MlDatasetSample,
    ModelVersion,
    MonthlyTurnover,
    RatingScale,
    ScorecardBin,
    ScoreFeatureValue,
    ScoreResult,
    StopFactor,
    StopFactorResult,
    TaxDebt,
    User,
    UserCompanyLink,
    ZskStatus,
)

SORTS = {"score", "-score", "pd", "-pd", "as_of", "-as_of", "name", "-name"}


@dataclass
class CompanyFilters:
    q: str | None = None
    decision: str | None = (
        None  # approve / counter_offer / manual_review / decline / none
    )
    segment: str | None = None  # сегмент по правилам
    model: str | None = None  # model_name
    grade: str | None = None
    fact: str | None = None  # default / no_default / unknown
    source: str | None = None  # synthetic / live
    score_min: float | None = None
    score_max: float | None = None
    as_of_from: date | None = None
    as_of_to: date | None = None
    borderline: float | None = None  # баллы в ±N от границы грейда
    hard_stop: bool | None = None


def latest_scores():
    """Последний скоринг каждой компании."""
    return (
        select(ScoreResult)
        .distinct(ScoreResult.company_id)
        .order_by(ScoreResult.company_id, ScoreResult.calculated_at.desc())
        .subquery("ls")
    )


def _has_default():
    return exists().where(DefaultEvent.company_id == Company.id)


def _base(ls, filters: CompanyFilters) -> Select:
    sample = (
        select(MlDatasetSample.company_id, MlDatasetSample.target)
        .distinct(MlDatasetSample.company_id)
        .subquery("smp")
    )
    fact = case(
        (_has_default(), literal("default")),
        (sample.c.company_id.is_not(None), literal("no_default")),
        else_=literal("unknown"),
    ).label("fact")
    source = case(
        (sample.c.company_id.is_not(None), literal("synthetic")), else_=literal("live")
    ).label("source")
    stmt = (
        select(
            Company,
            ls.c.id.label("score_id"),
            ls.c.total_score,
            ls.c.pd,
            ls.c.grade,
            ls.c.recommended_decision,
            ls.c.segment_code,
            ls.c.as_of_date,
            ls.c.has_hard_stop,
            ls.c.calculated_at,
            ModelVersion.model_name,
            ModelVersion.version,
            ModelVersion.segment_code.label("model_segment"),
            fact,
            source,
        )
        .outerjoin(ls, ls.c.company_id == Company.id)
        .outerjoin(ModelVersion, ModelVersion.id == ls.c.model_version_id)
        .outerjoin(sample, sample.c.company_id == Company.id)
    )
    f = filters
    conds = []
    if f.q:
        like = f"%{f.q.strip()}%"
        conds.append(
            or_(
                Company.full_name.ilike(like),
                Company.short_name.ilike(like),
                Company.inn.like(f"{f.q.strip()}%"),
            )
        )
    if f.decision == "none":
        conds.append(ls.c.recommended_decision.is_(None))
    elif f.decision:
        conds.append(ls.c.recommended_decision == f.decision)
    if f.segment:
        conds.append(ls.c.segment_code == f.segment)
    if f.model:
        conds.append(ModelVersion.model_name == f.model)
    if f.grade:
        conds.append(ls.c.grade.in_([g.strip() for g in f.grade.split(",")]))
    if f.fact == "default":
        conds.append(_has_default())
    elif f.fact == "no_default":
        conds.append(and_(~_has_default(), sample.c.company_id.is_not(None)))
    elif f.fact == "unknown":
        conds.append(and_(~_has_default(), sample.c.company_id.is_(None)))
    if f.source == "synthetic":
        conds.append(sample.c.company_id.is_not(None))
    elif f.source == "live":
        conds.append(sample.c.company_id.is_(None))
    if f.score_min is not None:
        conds.append(ls.c.total_score >= f.score_min)
    if f.score_max is not None:
        conds.append(ls.c.total_score <= f.score_max)
    if f.as_of_from:
        conds.append(ls.c.as_of_date >= f.as_of_from)
    if f.as_of_to:
        conds.append(ls.c.as_of_date <= f.as_of_to)
    if f.hard_stop is not None:
        conds.append(ls.c.has_hard_stop.is_(f.hard_stop))
    if f.borderline is not None:
        conds.append(
            exists().where(
                RatingScale.model_version_id == ls.c.model_version_id,
                RatingScale.score_from > -9000,
                func.abs(ls.c.total_score - RatingScale.score_from) <= f.borderline,
            )
        )
    return stmt.where(*conds) if conds else stmt


async def list_companies(
    session: AsyncSession,
    filters: CompanyFilters,
    *,
    limit: int,
    offset: int,
    sort: str = "-as_of",
    random_seed: int | None = None,
) -> tuple[int, list]:
    ls = latest_scores()
    stmt = _base(ls, filters)
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    if random_seed is not None:
        order = [func.md5(func.concat(cast(Company.id, Text), str(random_seed)))]
    else:
        key = sort.lstrip("-")
        col = {
            "score": ls.c.total_score,
            "pd": ls.c.pd,
            "as_of": ls.c.as_of_date,
            "name": Company.full_name,
        }.get(key, ls.c.as_of_date)
        order = [
            (col.desc() if sort.startswith("-") else col.asc()).nulls_last(),
            Company.id,
        ]
    rows = (
        await session.execute(stmt.order_by(*order).limit(limit).offset(offset))
    ).all()
    return total, rows


async def summary(session: AsyncSession) -> dict[str, Any]:
    ls = latest_scores()
    synthetic = (
        await session.execute(
            select(func.count(func.distinct(MlDatasetSample.company_id)))
        )
    ).scalar_one()
    companies = (await session.execute(select(func.count(Company.id)))).scalar_one()
    by_decision = dict(
        (
            await session.execute(
                select(ls.c.recommended_decision, func.count()).group_by(
                    ls.c.recommended_decision
                )
            )
        ).all()
    )
    approved_defaults = (
        await session.execute(
            select(func.count())
            .select_from(ls)
            .where(
                ls.c.recommended_decision == "approve",
                exists().where(DefaultEvent.company_id == ls.c.company_id),
            )
        )
    ).scalar_one()
    approved_known = (
        await session.execute(
            select(func.count())
            .select_from(ls)
            .where(
                ls.c.recommended_decision == "approve",
                exists().where(MlDatasetSample.company_id == ls.c.company_id),
            )
        )
    ).scalar_one()
    last = (
        await session.execute(select(func.max(ScoreResult.calculated_at)))
    ).scalar_one()
    return {
        "companies": companies,
        "synthetic": synthetic,
        "by_decision": {(k.value if k else "none"): v for k, v in by_decision.items()},
        "approved_defaults": approved_defaults,
        "approved_known": approved_known,
        "last_scored_at": last,
    }


# --------------------------------------------------------------- карточка


async def company_users(session: AsyncSession, company_id: uuid.UUID) -> list:
    stmt = (
        select(User, UserCompanyLink.role, UserCompanyLink.status)
        .join(UserCompanyLink, UserCompanyLink.user_id == User.id)
        .where(UserCompanyLink.company_id == company_id)
    )
    return list((await session.execute(stmt)).all())


async def company_okveds(session: AsyncSession, company_id: uuid.UUID) -> list:
    stmt = select(CompanyOkved).where(CompanyOkved.company_id == company_id)
    return list((await session.execute(stmt)).scalars().all())


async def score_history(session: AsyncSession, company_id: uuid.UUID) -> list:
    stmt = (
        select(ScoreResult, ModelVersion.model_name, ModelVersion.version)
        .join(ModelVersion, ModelVersion.id == ScoreResult.model_version_id)
        .where(ScoreResult.company_id == company_id)
        .order_by(ScoreResult.calculated_at.desc())
    )
    return list((await session.execute(stmt)).all())


async def score_contributions(session: AsyncSession, score_id: uuid.UUID) -> list:
    stmt = (
        select(ScoreFeatureValue, ScorecardBin, FeatureDefinition.name)
        .outerjoin(ScorecardBin, ScorecardBin.id == ScoreFeatureValue.bin_id)
        .outerjoin(
            FeatureDefinition, FeatureDefinition.code == ScoreFeatureValue.feature_code
        )
        .where(ScoreFeatureValue.score_result_id == score_id)
    )
    return list((await session.execute(stmt)).all())


async def best_points(session: AsyncSession, model_id: uuid.UUID) -> dict[str, float]:
    stmt = (
        select(ScorecardBin.feature_code, func.max(ScorecardBin.points))
        .where(ScorecardBin.model_version_id == model_id)
        .group_by(ScorecardBin.feature_code)
    )
    return {f: float(p) for f, p in (await session.execute(stmt)).all()}


async def score_stops(session: AsyncSession, score_id: uuid.UUID) -> list:
    stmt = (
        select(StopFactorResult, StopFactor.name)
        .join(StopFactor, StopFactor.code == StopFactorResult.stop_factor_code)
        .where(StopFactorResult.score_result_id == score_id)
    )
    return list((await session.execute(stmt)).all())


async def default_event(session: AsyncSession, company_id: uuid.UUID):
    stmt = (
        select(DefaultEvent)
        .where(DefaultEvent.company_id == company_id)
        .order_by(DefaultEvent.default_date)
    )
    return (await session.execute(stmt)).scalars().first()


async def company_sources(session: AsyncSession, company_id: uuid.UUID) -> dict:
    async def all_of(stmt):
        return list((await session.execute(stmt)).scalars().all())

    turnovers = (
        await session.execute(
            select(
                MonthlyTurnover.month,
                func.sum(MonthlyTurnover.inflow),
                func.sum(MonthlyTurnover.outflow),
                func.sum(MonthlyTurnover.closing_balance),
            )
            .join(BankAccount, BankAccount.id == MonthlyTurnover.account_id)
            .where(BankAccount.company_id == company_id)
            .group_by(MonthlyTurnover.month)
            .order_by(MonthlyTurnover.month)
        )
    ).all()
    return {
        "obligations": await all_of(
            select(CreditObligation)
            .where(CreditObligation.company_id == company_id)
            .order_by(CreditObligation.opened_at.desc().nulls_last())
        ),
        "turnovers": turnovers,
        "accounts": await all_of(
            select(BankAccount).where(BankAccount.company_id == company_id)
        ),
        "tax": await all_of(
            select(TaxDebt)
            .where(TaxDebt.company_id == company_id)
            .order_by(TaxDebt.as_of_date.desc())
        ),
        "fssp": await all_of(
            select(EnforcementProceeding)
            .where(EnforcementProceeding.company_id == company_id)
            .order_by(EnforcementProceeding.opened_at.desc())
        ),
        "zsk": await all_of(
            select(ZskStatus)
            .where(ZskStatus.company_id == company_id)
            .order_by(ZskStatus.as_of_date.desc())
        ),
        "bankruptcy": await all_of(
            select(BankruptcyEvent).where(BankruptcyEvent.company_id == company_id)
        ),
        "fetches": await all_of(
            select(DataFetch)
            .where(DataFetch.company_id == company_id)
            .order_by(DataFetch.requested_at.desc())
            .limit(50)
        ),
    }


# --------------------------------------------------------------- срезы


async def decision_fact_matrix(
    session: AsyncSession, filters: CompanyFilters
) -> list[tuple[str | None, str, int]]:
    ls = latest_scores()
    base = _base(ls, filters).subquery("b")
    stmt = select(base.c.recommended_decision, base.c.fact, func.count()).group_by(
        base.c.recommended_decision, base.c.fact
    )
    return [
        (d.value if hasattr(d, "value") else d, f, c)
        for d, f, c in (await session.execute(stmt)).all()
    ]


async def group_features(
    session: AsyncSession, filters: CompanyFilters, limit: int = 3000
) -> list[dict]:
    ls = latest_scores()
    base = _base(ls, filters).subquery("b")
    stmt = (
        select(ScoreResult.features)
        .join(base, base.c.score_id == ScoreResult.id)
        .where(ScoreResult.features.is_not(None))
        .order_by(func.md5(cast(ScoreResult.id, Text)))
        .limit(limit)
    )
    return [r for r in (await session.execute(stmt)).scalars().all() if r]


async def monthly(session: AsyncSession, filters: CompanyFilters) -> list:
    ls = latest_scores()
    base = _base(ls, filters).subquery("b")
    month = func.date_trunc("month", cast(base.c.as_of_date, DateTime)).label("month")
    stmt = (
        select(
            month,
            func.count(),
            func.avg(case((base.c.recommended_decision == "approve", 1.0), else_=0.0)),
            func.avg(base.c.pd),
            func.avg(case((base.c.fact == "default", 1.0), else_=0.0)),
            func.sum(case((base.c.fact == "unknown", 0), else_=1)),
            func.avg(base.c.total_score),
        )
        .where(base.c.as_of_date.is_not(None))
        .group_by(month)
        .order_by(month)
    )
    return list((await session.execute(stmt)).all())


async def random_scored_many(
    session: AsyncSession, filters: CompanyFilters, seed: int, limit: int
) -> list[Any]:
    """Случайные оскоренные компании под фильтры — с входами модели и фактом."""
    ls = latest_scores()
    base = _base(ls, filters).where(ls.c.id.is_not(None)).subquery("b")
    stmt = (
        select(
            ScoreResult.features,
            base.c.id,
            base.c.full_name,
            base.c.model_name,
            base.c.recommended_decision,
            base.c.has_hard_stop,
            base.c.fact,
        )
        .join(base, base.c.score_id == ScoreResult.id)
        .order_by(func.md5(func.concat(cast(base.c.id, Text), str(seed))))
        .limit(limit)
    )
    return list((await session.execute(stmt)).all())


async def random_scored(
    session: AsyncSession, filters: CompanyFilters, seed: int
) -> Any | None:
    ls = latest_scores()
    base = _base(ls, filters).where(ls.c.id.is_not(None)).subquery("b")
    stmt = (
        select(ScoreResult.features, base.c.id, base.c.full_name)
        .join(base, base.c.score_id == ScoreResult.id)
        .order_by(func.md5(func.concat(cast(base.c.id, Text), str(seed))))
        .limit(1)
    )
    return (await session.execute(stmt)).first()
