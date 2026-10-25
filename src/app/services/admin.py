"""Кабинет администратора: вход сотрудника, сводка, компании, разбор скоринга, модели, срезы."""

import statistics
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.credit.features import FEATURE_CATALOG
from app.credit.recommendation import DECISION_LABEL, recommend
from app.credit.scorecard import OTHER, ScoreOutcome, score
from app.enums import DecisionType, StaffRole
from app.exceptions import InvalidCredentailsError, NotFoundError
from app.models import AuditLog, Company, ModelVersion, ScorecardBin, StaffUser
from app.repositories import admin as admin_repo
from app.repositories import scoring as scoring_repo
from app.repositories.admin import CompanyFilters
from app.security import create_staff_token, verify_password
from app.services import rescoring

CATEGORICAL = {
    "legal_form",
    "msp_category",
    "okved_section",
    "region_code",
    "tax_regime",
    "zsk_zone",
}


def _num(v) -> float | None:
    return float(v) if isinstance(v, Decimal | int | float) else None


def _dec(d) -> str | None:
    if d is None:
        return None
    return d.value if isinstance(d, DecisionType) else str(d)


def decision_label(d) -> str | None:
    if d is None:
        return None
    return DECISION_LABEL.get(DecisionType(_dec(d)), str(d))


def feature_name(code: str) -> str:
    return FEATURE_CATALOG.get(code, (code,))[0]


def _bound(v) -> str:
    """Граница бина: большие суммы — «6,39 млн», остальное — до 4 значащих цифр."""
    x = float(v)
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:.3g} млн".replace(".", ",")
    if abs(x) >= 10_000:
        return f"{x / 1_000:.3g} тыс".replace(".", ",")
    return f"{x:.4g}"


def bin_label(b: ScorecardBin | dict | None) -> str:
    if b is None:
        return "нейтрально (нет бина)"
    get = b.get if isinstance(b, dict) else lambda k: getattr(b, k)
    if get("is_missing_bin"):
        return "пропуск"
    cats = get("categories")
    if cats:
        return ", ".join("прочие" if c == OTHER else c for c in cats)
    lo, hi = get("lower_bound"), get("upper_bound")
    fmt = _bound
    if lo is None and hi is None:
        return "любое"
    if lo is None:
        return f"< {fmt(hi)}"
    if hi is None:
        return f"≥ {fmt(lo)}"
    return f"[{fmt(lo)}; {fmt(hi)})"


async def audit(
    session: AsyncSession,
    staff: StaffUser,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    diff: dict | None = None,
    ip: str | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_type="staff",
            actor_id=staff.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            diff=diff,
            ip=ip,
        )
    )


# --------------------------------------------------------------- вход


async def login(
    session: AsyncSession, login_: str, password: str, ip: str | None
) -> tuple[str, StaffUser]:
    staff = (
        await session.execute(select(StaffUser).where(StaffUser.login == login_))
    ).scalar_one_or_none()
    if (
        staff is None
        or not staff.password_hash
        or not staff.is_active
        or staff.role != StaffRole.ADMIN
        or not verify_password(password, staff.password_hash)
    ):
        raise InvalidCredentailsError
    staff.last_login_at = datetime.now(UTC)
    await audit(session, staff, "admin_login", "staff_user", staff.id, ip=ip)
    await session.commit()
    return create_staff_token(staff.id), staff


def staff_view(staff: StaffUser) -> dict:
    return {
        "id": str(staff.id),
        "login": staff.login,
        "fullName": staff.full_name,
        "role": staff.role.value,
    }


# --------------------------------------------------------------- компании


def _row(r) -> dict[str, Any]:
    c: Company = r.Company
    return {
        "id": str(c.id),
        "name": c.short_name or c.full_name,
        "inn": c.inn,
        "legalForm": c.legal_form,
        "msp": c.msp_category.value if c.msp_category else None,
        "region": c.region_code,
        "status": c.status.value if c.status else None,
        "source": r.source,
        "segment": r.segment_code,
        "model": r.model_name,
        "modelVersion": r.version,
        "modelSegment": r.model_segment,
        "score": _num(r.total_score),
        "pd": _num(r.pd),
        "grade": r.grade,
        "decision": _dec(r.recommended_decision),
        "decisionLabel": decision_label(r.recommended_decision),
        "hardStop": bool(r.has_hard_stop) if r.score_id else None,
        "fact": r.fact,
        "asOf": r.as_of_date.isoformat() if r.as_of_date else None,
        "scoredAt": r.calculated_at.isoformat() if r.calculated_at else None,
    }


async def list_companies(
    session: AsyncSession,
    filters: CompanyFilters,
    *,
    limit: int,
    offset: int,
    sort: str,
    random_seed: int | None,
) -> dict:
    total, rows = await admin_repo.list_companies(
        session, filters, limit=limit, offset=offset, sort=sort, random_seed=random_seed
    )
    return {"total": total, "items": [_row(r) for r in rows]}


async def summary(session: AsyncSession) -> dict:
    s = await admin_repo.summary(session)
    by = s["by_decision"]
    scored = sum(v for k, v in by.items() if k != "none")
    share = lambda k: round(by.get(k, 0) / scored, 4) if scored else None
    return {
        "companies": s["companies"],
        "synthetic": s["synthetic"],
        "live": s["companies"] - s["synthetic"],
        "scored": scored,
        "byDecision": by,
        "approveShare": share("approve"),
        "manualShare": share("manual_review"),
        "declineShare": share("decline"),
        "defaultAmongApproved": round(s["approved_defaults"] / s["approved_known"], 4)
        if s["approved_known"]
        else None,
        "lastScoredAt": s["last_scored_at"].isoformat()
        if s["last_scored_at"]
        else None,
    }


def _outcome_view(outcome: ScoreOutcome, bins_by_feature: dict) -> list[dict]:
    rows = []
    for c in outcome.contributions:
        b = next(
            (
                x
                for x in bins_by_feature.get(c.feature, [])
                if x.bin_order == c.bin_order
            ),
            None,
        )
        rows.append(
            {
                "feature": c.feature,
                "name": feature_name(c.feature),
                "value": c.value,
                "bin": bin_label(b),
                "points": c.points,
                "best": c.max_points,
                "lost": round(c.max_points - c.points, 2),
                "eventRate": _num(b.event_rate) if b else None,
            }
        )
    return sorted(rows, key=lambda x: x["lost"], reverse=True)


async def _bins_by_feature(session: AsyncSession, model_id: uuid.UUID) -> dict:
    out: dict = {}
    for b in await scoring_repo.model_bins(session, model_id):
        out.setdefault(b.feature_code, []).append(b)
    return out


async def _score_with(session: AsyncSession, model: ModelVersion, features: dict):
    card = await scoring_repo.load_scorecard(session, model)
    return score(card, features)


async def company_card(session: AsyncSession, company_id: uuid.UUID) -> dict:
    company = await session.get(Company, company_id)
    if company is None:
        raise NotFoundError
    history = await admin_repo.score_history(session, company_id)
    data_input = await rescoring.company_input(session, company)
    latest = history[0].ScoreResult if history else None
    features = latest.features if latest and latest.features else data_input.features

    detail = None
    if latest is not None:
        model = await session.get(ModelVersion, latest.model_version_id)
        bins = await _bins_by_feature(session, model.id)
        outcome = await _score_with(session, model, features)
        stops = await admin_repo.score_stops(session, latest.id)
        grades = await scoring_repo.model_grades(session, model.id)
        upper = sorted(
            float(g.score_from)
            for g in grades
            if float(g.score_from) > float(latest.total_score or 0)
        )
        detail = {
            "scoreId": str(latest.id),
            "model": model.model_name,
            "modelVersion": model.version,
            "modelId": str(model.id),
            "modelSegment": model.segment_code,
            "segment": latest.segment_code,
            "score": _num(latest.total_score),
            "base": float((model.params or {}).get("intercept_points", 0)),
            "pd": _num(latest.pd),
            "grade": latest.grade,
            "nextGradeAt": upper[0] if upper else None,
            "decision": _dec(latest.recommended_decision),
            "decisionLabel": decision_label(latest.recommended_decision),
            "hardStop": latest.has_hard_stop,
            "reasonCodes": latest.reason_codes or [],
            "reasons": [feature_name(c) for c in latest.reason_codes or []],
            "asOf": latest.as_of_date.isoformat(),
            "scoredAt": latest.calculated_at.isoformat(),
            "inputSha256": latest.input_sha256,
            "contributions": _outcome_view(outcome, bins),
            "stops": [
                {
                    "code": s.StopFactorResult.stop_factor_code,
                    "name": s.name,
                    "triggered": s.StopFactorResult.triggered,
                }
                for s in stops
            ],
        }

    alternatives = []
    for m in await scoring_repo.list_models(session):
        out = await _score_with(session, m, features)
        alternatives.append(
            {
                "model": m.model_name,
                "version": m.version,
                "segment": m.segment_code,
                "status": m.status.value,
                "score": out.score,
                "grade": out.grade,
                "pd": out.pd,
                "decisionLabel": decision_label(_grade_decision(out.grade)),
                "isCurrent": latest is not None and m.id == latest.model_version_id,
            }
        )

    default = await admin_repo.default_event(session, company_id)
    sample = await scoring_repo.dataset_sample(session, company_id)
    src = await admin_repo.company_sources(session, company_id)
    users = await admin_repo.company_users(session, company_id)
    okveds = await admin_repo.company_okveds(session, company_id)
    return {
        "company": {
            "id": str(company.id),
            "name": company.short_name or company.full_name,
            "fullName": company.full_name,
            "inn": company.inn,
            "ogrn": company.ogrn,
            "legalForm": company.legal_form,
            "msp": company.msp_category.value if company.msp_category else None,
            "headcount": company.headcount,
            "taxRegime": company.tax_regime.value if company.tax_regime else None,
            "region": company.region_code,
            "address": company.legal_address,
            "registrationDate": company.registration_date.isoformat()
            if company.registration_date
            else None,
            "status": company.status.value if company.status else None,
            "okved": [o.okved_code for o in okveds],
            "source": data_input.source,
            "dataset": sample.dataset_code if sample else None,
            "sample": sample.sample if sample else None,
        },
        "fact": {
            "known": data_input.source == "synthetic",
            "default": default is not None,
            "defaultDate": default.default_date.isoformat() if default else None,
            "trigger": default.trigger.value if default else None,
        },
        "users": [
            {
                "name": f"{u.User.last_name} {u.User.first_name}",
                "email": u.User.email,
                "role": u.role.value,
                "status": u.status.value,
            }
            for u in users
        ],
        "features": features,
        "score": detail,
        "alternatives": alternatives,
        "history": [
            {
                "id": str(h.ScoreResult.id),
                "model": h.model_name,
                "version": h.version,
                "score": _num(h.ScoreResult.total_score),
                "grade": h.ScoreResult.grade,
                "pd": _num(h.ScoreResult.pd),
                "decisionLabel": decision_label(h.ScoreResult.recommended_decision),
                "asOf": h.ScoreResult.as_of_date.isoformat(),
                "scoredAt": h.ScoreResult.calculated_at.isoformat(),
            }
            for h in history
        ],
        "sources": _sources_view(src),
    }


def _grade_decision(grade: str | None):
    return recommend(grade, False)


def _sources_view(src: dict) -> dict:
    return {
        "obligations": [
            {
                "lender": o.lender_name,
                "product": o.product_type.value if o.product_type else None,
                "limit": _num(o.limit_amount),
                "outstanding": _num(o.outstanding),
                "overdue": _num(o.overdue_amount),
                "maxDpd": o.max_dpd,
                "openedAt": o.opened_at.isoformat() if o.opened_at else None,
                "closedAt": o.closed_at.isoformat() if o.closed_at else None,
                "paymentString": o.payment_string,
                "source": o.source.value,
            }
            for o in src["obligations"]
        ],
        "turnovers": [
            {
                "month": m.isoformat()[:7],
                "inflow": _num(i),
                "outflow": _num(o),
                "balance": _num(b),
            }
            for m, i, o, b in src["turnovers"]
        ],
        "accounts": [
            {"bik": a.bank_bik, "account": a.account_masked, "ownBank": a.is_own_bank}
            for a in src["accounts"]
        ],
        "tax": [
            {
                "asOf": t.as_of_date.isoformat(),
                "debt": _num(t.tax_debt),
                "penalties": _num(t.penalties),
                "fines": _num(t.fines),
            }
            for t in src["tax"]
        ],
        "fssp": [
            {
                "number": f.ip_number,
                "openedAt": f.opened_at.isoformat(),
                "closedAt": f.closed_at.isoformat() if f.closed_at else None,
                "subject": f.subject,
                "amount": _num(f.amount),
                "remaining": _num(f.remaining_amount),
            }
            for f in src["fssp"]
        ],
        "zsk": [
            {"zone": z.zone.value, "asOf": z.as_of_date.isoformat()} for z in src["zsk"]
        ],
        "bankruptcy": [
            {
                "caseNumber": b.case_number,
                "type": b.event_type,
                "date": b.event_date.isoformat(),
            }
            for b in src["bankruptcy"]
        ],
        "fetches": [
            {
                "id": str(f.id),
                "source": f.source.value,
                "status": f.status.value,
                "requestedAt": f.requested_at.isoformat(),
                "payload": f.raw_payload,
            }
            for f in src["fetches"]
        ],
    }


async def rescore(
    session: AsyncSession, staff: StaffUser, company_id: uuid.UUID, ip: str | None
) -> dict:
    company = await session.get(Company, company_id)
    if company is None:
        raise NotFoundError
    result = await rescoring.score_and_save(session, company)
    await audit(
        session,
        staff,
        "rescore",
        "company",
        company_id,
        {"score": float(result.total_score), "grade": result.grade},
        ip,
    )
    await session.commit()
    return await company_card(session, company_id)


# --------------------------------------------------------------- модели


async def list_models(session: AsyncSession) -> dict:
    segments = await scoring_repo.all_segments(session)
    return {
        "models": [
            {
                "id": str(m.id),
                "name": m.model_name,
                "version": m.version,
                "type": m.model_type,
                "segment": m.segment_code,
                "status": m.status.value,
                "giniTrain": _num(m.gini_train),
                "giniOot": _num(m.gini_oot),
                "ksOot": _num(m.ks_oot),
                "cutoff": _num(m.cutoff_score),
                "params": m.params or {},
                "trainFrom": m.train_from.isoformat() if m.train_from else None,
                "trainTo": m.train_to.isoformat() if m.train_to else None,
                "ootFrom": m.oot_from.isoformat() if m.oot_from else None,
                "ootTo": m.oot_to.isoformat() if m.oot_to else None,
                "target": m.target_definition,
            }
            for m in await scoring_repo.list_models(session)
        ],
        "segments": [
            {
                "code": s.code,
                "name": s.name,
                "description": s.description,
                "priority": s.priority,
                "conditions": s.conditions,
                "isActive": s.is_active,
            }
            for s in segments
        ],
    }


async def model_detail(session: AsyncSession, model_id: uuid.UUID) -> dict:
    m = await scoring_repo.get_model(session, model_id)
    if m is None:
        raise NotFoundError
    feats = {
        f.feature_code: f for f in await scoring_repo.model_features(session, m.id)
    }
    bins = await _bins_by_feature(session, m.id)
    features = []
    for code, items in bins.items():
        mf = feats.get(code)
        features.append(
            {
                "code": code,
                "name": feature_name(code),
                "kind": "categorical" if code in CATEGORICAL else "numeric",
                "coefficient": _num(mf.coefficient) if mf else None,
                "iv": _num(mf.information_value) if mf else None,
                "formula": FEATURE_CATALOG.get(code, ("", "", "", ""))[3],
                "bins": [
                    {
                        "order": b.bin_order,
                        "label": bin_label(b),
                        "lower": _num(b.lower_bound),
                        "upper": _num(b.upper_bound),
                        "categories": b.categories,
                        "isMissing": b.is_missing_bin,
                        "points": float(b.points),
                        "woe": float(b.woe),
                        "eventRate": _num(b.event_rate),
                        "share": _num(b.population_share),
                    }
                    for b in items
                ],
            }
        )
    features.sort(key=lambda f: -(f["iv"] or 0))
    grades = await scoring_repo.model_grades(session, m.id)
    return {
        "id": str(m.id),
        "name": m.model_name,
        "version": m.version,
        "segment": m.segment_code,
        "status": m.status.value,
        "base": float((m.params or {}).get("intercept_points", 0)),
        "params": m.params or {},
        "features": features,
        "grades": [
            {
                "grade": g.grade,
                "from": float(g.score_from),
                "to": float(g.score_to),
                "pd": float(g.pd_calibrated),
            }
            for g in grades
        ],
    }


async def calculate(session: AsyncSession, model_id: uuid.UUID, features: dict) -> dict:
    m = await scoring_repo.get_model(session, model_id)
    if m is None:
        raise NotFoundError
    outcome = await _score_with(session, m, features)
    bins = await _bins_by_feature(session, m.id)
    return {
        "score": outcome.score,
        "pd": outcome.pd,
        "grade": outcome.grade,
        "decisionLabel": decision_label(_grade_decision(outcome.grade)),
        "reasons": [feature_name(c) for c in outcome.reason_codes()],
        "contributions": _outcome_view(outcome, bins),
    }


async def example(
    session: AsyncSession, filters: CompanyFilters, seed: int
) -> dict | None:
    row = await admin_repo.random_scored(session, filters, seed)
    if row is None:
        return None
    return {"companyId": str(row.id), "name": row.full_name, "features": row.features}


# --------------------------------------------------------------- срезы


async def matrix(session: AsyncSession, filters: CompanyFilters) -> dict:
    cells = await admin_repo.decision_fact_matrix(session, filters)
    return {
        "cells": [
            {
                "decision": d,
                "decisionLabel": decision_label(d) or "без скоринга",
                "fact": f,
                "count": c,
            }
            for d, f, c in cells
        ]
    }


def _profile(rows: list[dict]) -> dict:
    out: dict = {}
    for code in FEATURE_CATALOG:
        values = [r.get(code) for r in rows if r.get(code) is not None]
        if not values:
            continue
        if code in CATEGORICAL:
            counts: dict = {}
            for v in values:
                counts[v] = counts.get(v, 0) + 1
            top = max(counts, key=counts.get)
            out[code] = {
                "kind": "cat",
                "top": top,
                "share": counts[top] / len(values),
                "counts": counts,
                "n": len(values),
            }
        else:
            nums = [float(v) for v in values]
            q = (
                statistics.quantiles(nums, n=4)
                if len(nums) >= 4
                else [min(nums), statistics.median(nums), max(nums)]
            )
            out[code] = {
                "kind": "num",
                "median": statistics.median(nums),
                "iqr": q[2] - q[0],
                "mean": statistics.fmean(nums),
                "n": len(nums),
            }
    return out


async def drivers(
    session: AsyncSession, group: CompanyFilters, reference: CompanyFilters
) -> dict:
    """Чем группа отличается от эталона: медианы признаков и доли категорий."""
    g_rows = await admin_repo.group_features(session, group)
    r_rows = await admin_repo.group_features(session, reference)
    g, r = _profile(g_rows), _profile(r_rows)
    items = []
    for code, gp in g.items():
        rp = r.get(code)
        if rp is None:
            continue
        if gp["kind"] == "num":
            scale = rp["iqr"] or abs(rp["median"]) or 1.0
            effect = (gp["median"] - rp["median"]) / scale
            items.append(
                {
                    "feature": code,
                    "name": feature_name(code),
                    "kind": "num",
                    "group": gp["median"],
                    "reference": rp["median"],
                    "effect": round(effect, 3),
                }
            )
        else:
            top = gp["top"]
            ref_share = rp["counts"].get(top, 0) / rp["n"]
            effect = (gp["share"] - ref_share) * 2
            items.append(
                {
                    "feature": code,
                    "name": feature_name(code),
                    "kind": "cat",
                    "top": top,
                    "group": round(gp["share"], 3),
                    "reference": round(ref_share, 3),
                    "effect": round(effect, 3),
                }
            )
    items.sort(key=lambda x: abs(x["effect"]), reverse=True)
    return {"groupSize": len(g_rows), "referenceSize": len(r_rows), "items": items[:10]}


async def monthly(session: AsyncSession, filters: CompanyFilters) -> dict:
    rows = await admin_repo.monthly(session, filters)
    return {
        "months": [
            {
                "month": m.date().isoformat()[:7] if hasattr(m, "date") else str(m)[:7],
                "n": n,
                "approveShare": _num(a),
                "avgPd": _num(p),
                "defaultRate": _num(d) if known else None,
                "avgScore": _num(s),
            }
            for m, n, a, p, d, known, s in rows
        ]
    }


async def disagreement(
    session: AsyncSession, filters: CompanyFilters, seed: int, sample: int
) -> dict:
    """Champion против остальных моделей на случайной выборке: где решения расходятся.

    Каждую компанию выборки пересчитываем всеми моделями на тех же входах и сравниваем
    рекомендацию с применённой. Для синтетики видно, какая модель реже пропускает дефолт.
    """
    rows = await admin_repo.random_scored_many(session, filters, seed, sample)
    models = await scoring_repo.list_models(session)
    cards = {m.id: (m, await scoring_repo.load_scorecard(session, m)) for m in models}

    stats = {
        m.id: {"agree": 0, "approve": 0, "approvedKnown": 0, "approvedDefault": 0}
        for m in models
    }
    examples = []
    for r in rows:
        if not r.features:
            continue
        current = r.recommended_decision
        decisions = {}
        for mid, (m, card) in cards.items():
            out = score(card, r.features)
            d = recommend(out.grade, bool(r.has_hard_stop))
            decisions[m.model_name] = d
            st = stats[mid]
            st["agree"] += d == current
            if d == DecisionType.APPROVE:
                st["approve"] += 1
                if r.fact != "unknown":
                    st["approvedKnown"] += 1
                    st["approvedDefault"] += r.fact == "default"
        distinct = {d for d in decisions.values() if d is not None}
        if len(distinct) > 1 and len(examples) < 30:
            examples.append(
                {
                    "id": str(r.id),
                    "name": r.full_name,
                    "model": r.model_name,
                    "fact": r.fact,
                    "decisionLabel": decision_label(current),
                    "byModel": {k: decision_label(v) for k, v in decisions.items()},
                }
            )
    n = sum(1 for r in rows if r.features)
    return {
        "sample": n,
        "seed": seed,
        "models": [
            {
                "model": m.model_name,
                "version": m.version,
                "segment": m.segment_code,
                "status": m.status.value,
                "agreeShare": stats[m.id]["agree"] / n if n else None,
                "approveShare": stats[m.id]["approve"] / n if n else None,
                "defaultAmongApproved": (
                    stats[m.id]["approvedDefault"] / stats[m.id]["approvedKnown"]
                    if stats[m.id]["approvedKnown"]
                    else None
                ),
            }
            for m in models
        ],
        "examples": examples,
    }
