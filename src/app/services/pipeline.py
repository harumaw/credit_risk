"""Конвейер заявки (CLAUDE.md §10): сбор данных → стоп-факторы → признаки → скоринг → лимит → решение.

Запускает воркер (`app.worker`) по задаче `process_application`. Обработка идемпотентна:
заявка не в статусе `submitted` (уже обработана или отменена) — задача ничего не делает.
Сбой источника после ретраев клиента — ручной разбор.
"""

import calendar
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.credit import reasons as texts
from app.credit.decision import (
    APPROVED,
    COUNTER_OFFER,
    DECLINED,
    Decision,
    DecisionInput,
    Offer,
    ProductTerms,
    decide,
)
from app.credit.exposure import OwnCredit, own_payments
from app.credit.features import (
    CompanyFacts,
    Obligation,
    TurnoverMonth,
    company_features,
    months_between,
)
from app.credit.limit import dscr
from app.credit.scorecard import ScoreOutcome
from app.credit.stop_factors import (
    BY_CODE,
    MIN_AGE_MONTHS,
    StopCheck,
    StopFacts,
    evaluate,
)
from app.enums import (
    ApplicationStatus,
    CompanyStatus,
    DecisionType,
    FetchStatus,
    StopSeverity,
)
from app.integrations.registry import Sources
from app.models import (
    Company,
    CreditDecision,
    CreditProduct,
    ScoreFeatureValue,
    ScoreResult,
    StopFactorResult,
)
from app.repositories import application as applications_repo
from app.repositories import company as companies_repo
from app.repositories import decision as decisions_repo
from app.repositories import external_data as data_repo
from app.services import company_data
from app.services.application import transition
from app.services.scoring import ModelChoice, NoScoringModel, score_company

HISTORY_MONTHS = 12
OFFER_VALID_DAYS = 30

_STATUS = {
    APPROVED: ApplicationStatus.APPROVED,
    COUNTER_OFFER: ApplicationStatus.APPROVED,
    DECLINED: ApplicationStatus.DECLINED,
}
_DECISION_TYPE = {
    APPROVED: DecisionType.APPROVE,
    COUNTER_OFFER: DecisionType.COUNTER_OFFER,
    DECLINED: DecisionType.DECLINE,
}
_COMMENT = {
    APPROVED: "Заявка одобрена — примите условия, чтобы перейти к подписанию",
    COUNTER_OFFER: "Одобрена сумма меньше запрошенной — посмотрите предложение",
    DECLINED: "Банк не может выдать кредит на этих условиях",
}


@dataclass(frozen=True)
class CompanyData:
    """Всё, что конвейер знает о компании на дату расчёта."""

    facts: CompanyFacts
    stop: StopFacts
    income: Decimal | None  # чистый поток в месяц за 12 мес
    inflow: Decimal | None  # приход в месяц за 12 мес
    payments: Decimal  # текущие платежи по кредитам в месяц: БКИ + наши
    own_payments: Decimal = Decimal(
        0
    )  # из них — по нашим кредитам и принятым предложениям


def _plus_months(day: date, months: int) -> date:
    year, month = divmod(day.month - 1 + months, 12)
    year += day.year
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last))


def _avg(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal(0)) / len(values) if values else None


def _own_obligation(c: OwnCredit, today: date) -> Obligation:
    """Наш выданный кредит как договор КИ: БКИ узнает о нём позже, считаем сразу."""
    return Obligation(
        limit_amount=float(c.amount),
        outstanding=float(c.outstanding(today)),
        monthly_payment=float(c.monthly_payment),
        opened_at=c.issued_at,
        closed_at=None,
        payment_string="",
    )


async def gather(
    session: AsyncSession,
    company: Company,
    today: date,
    exclude_application_id: uuid.UUID | None = None,
) -> CompanyData:
    months = (await data_repo.monthly_totals(session, [company.id]))[-HISTORY_MONTHS:]
    open_loans = await data_repo.open_obligations(session, [company.id], today)
    next_payment = {o.id: o.next_payment for o in open_loans}
    obligations = await data_repo.company_obligations(session, company.id)
    tax = await data_repo.latest_tax_debt(session, company.id)
    zsk = await data_repo.latest_zsk(session, company.id)
    fssp_cnt, fssp_rest = await data_repo.active_enforcements(
        session, company.id, today
    )
    okved = await companies_repo.list_company_okved(session, company.id)
    # Признак модели — недоимка (как в обучении), стоп-фактор — весь долг с пенями и штрафами
    tax_debt = tax.tax_debt or Decimal(0) if tax else Decimal(0)
    tax_total = (
        tax_debt + (tax.penalties or 0) + (tax.fines or 0) if tax else Decimal(0)
    )
    own = await applications_repo.own_credits(
        session, [company.id], exclude_application_id=exclude_application_id
    )
    reg = company.registration_date
    facts = CompanyFacts(
        as_of_date=today,
        legal_form=company.legal_form or "",
        registration_date=company.registration_date,
        msp_category=company.msp_category.value if company.msp_category else None,
        okved_main=next((code for code, _, main in okved if main), None),
        region_code=company.region_code,
        tax_regime=company.tax_regime.value if company.tax_regime else None,
        zsk_zone=zsk.zone.value if zsk else None,
        tax_debt=float(tax_debt),
        fssp_active_cnt=fssp_cnt,
        fssp_active_amount=float(fssp_rest),
        own_bank_client=await data_repo.has_own_bank_account(session, company.id),
        obligations=[
            Obligation(
                limit_amount=float(o.limit_amount or 0),
                outstanding=float(o.outstanding or 0),
                monthly_payment=float(next_payment.get(o.id, 0)),
                opened_at=o.opened_at,
                closed_at=o.closed_at,
                payment_string=o.payment_string or "",
            )
            for o in obligations
        ]
        + [_own_obligation(c, today) for c in own if c.issued_at is not None],
        turnovers=[
            TurnoverMonth(
                m.month, float(m.inflow), float(m.outflow), float(m.closing_balance)
            )
            for m in months
        ],
    )
    stop = StopFacts(
        company_active=company.status == CompanyStatus.ACTIVE,
        bankruptcy_messages=await data_repo.count_bankruptcy_events(
            session, company.id
        ),
        zsk_zone=facts.zsk_zone,
        age_months=months_between(company.registration_date, today)
        if company.registration_date
        else None,
        tax_debt=Decimal(tax_total),
        fssp_remaining=fssp_rest,
        current_overdue=sum((o.overdue for o in open_loans), Decimal(0)),
        worst_dpd=await data_repo.worst_past_dpd(session, company.id),
        eligible_from=_plus_months(reg, MIN_AGE_MONTHS) if reg else None,
    )
    return CompanyData(
        facts=facts,
        stop=stop,
        income=_avg([m.inflow - m.outflow for m in months]),
        inflow=_avg([m.inflow for m in months]),
        payments=sum(next_payment.values(), Decimal(0)) + own_payments(own),
        own_payments=own_payments(own),
    )


def product_terms(p: CreditProduct) -> ProductTerms:
    return ProductTerms(
        code=p.code,
        name=p.name,
        kind=p.product_type.value,
        min_amount=p.min_amount or Decimal(0),
        max_amount=p.max_amount or Decimal(0),
        min_term=p.min_term_months or 1,
        max_term=p.max_term_months or 1,
        base_rate=p.base_rate or Decimal(0),
    )


def _offer_json(o: Offer) -> dict:
    return {
        "productCode": o.product_code,
        "productName": o.product_name,
        "amount": int(o.amount),
        "termMonths": o.term_months,
        "rate": float(o.rate),
        "monthlyPayment": int(o.monthly_payment),
    }


def _sha256(features: dict) -> str:
    raw = json.dumps(features, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


async def _save_score(
    session: AsyncSession,
    application_id: uuid.UUID,
    company_id: uuid.UUID,
    today: date,
    features: dict,
    scored: tuple[ModelChoice, ScoreOutcome],
    checks: list[StopCheck],
    hard_stop: bool,
    latency_ms: int,
) -> ScoreResult:
    choice, outcome = scored
    known = await decisions_repo.known_features(
        session, [c.feature for c in outcome.contributions]
    )
    values = [
        ScoreFeatureValue(
            feature_code=c.feature,
            value_num=Decimal(str(c.value))
            if isinstance(c.value, int | float)
            else None,
            value_text=c.value if isinstance(c.value, str) else None,
            points=Decimal(str(round(c.points, 2))),
        )
        for c in outcome.contributions
        if c.feature in known
    ]
    stops = [
        StopFactorResult(
            stop_factor_code=c.code, triggered=c.triggered, details=c.details
        )
        for c in checks
    ]
    result = ScoreResult(
        application_id=application_id,
        company_id=company_id,
        model_version_id=choice.model.id,
        as_of_date=today,
        total_score=Decimal(str(outcome.score)),
        pd=Decimal(str(outcome.pd)),
        grade=outcome.grade,
        has_hard_stop=hard_stop,
        input_sha256=_sha256(features),
        latency_ms=latency_ms,
    )
    return await decisions_repo.add_score_result(session, result, values, stops)


async def process_application(
    session: AsyncSession, sources: Sources, application_id: uuid.UUID
) -> None:
    application = await applications_repo.lock_application(session, application_id)
    if application is None:
        return
    if application.status == ApplicationStatus.SUBMITTED:
        await transition(
            session,
            application,
            ApplicationStatus.SCORING,
            "Собираем данные о компании и оцениваем заявку",
        )
        await session.commit()  # клиент сразу видит «проверяем»
    elif application.status != ApplicationStatus.SCORING:
        return  # уже решена или отменена; scoring — повтор после сбоя, считаем заново

    row = await applications_repo.get_application_row(session, application_id)
    assert row is not None
    application, company, product = row
    started = time.monotonic()
    fetches = await company_data.collect(session, sources, company)
    today = datetime.now(UTC).date()
    data = await gather(session, company, today, exclude_application_id=application.id)
    features = company_features(data.facts)
    checks = evaluate(data.stop)
    hard_stop = any(
        c.triggered and BY_CODE[c.code].severity == StopSeverity.HARD for c in checks
    )
    scored: tuple[ModelChoice, ScoreOutcome] | None = None
    if not hard_stop:  # стоп-факторы до скоринга: жёсткий стоп — отказ без балла
        try:
            scored = await score_company(session, features)
        except NoScoringModel:
            scored = None
    products = await applications_repo.list_active_products(session)
    decision = decide(
        DecisionInput(
            product=product_terms(product),
            requested_amount=application.requested_amount or Decimal(0),
            requested_term=application.requested_term_months or 1,
            stop_checks=checks,
            income=data.income,
            payments=data.payments,
            monthly_inflow=data.inflow,
            own_bank_client=data.facts.own_bank_client,
            grade=scored[1].grade if scored else None,
            score_reasons=scored[1].reason_codes() if scored else [],
            products=[product_terms(p) for p in products],
            source_error=any(f.status == FetchStatus.ERROR for f in fetches),
        )
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    application = await applications_repo.lock_application(session, application_id)
    if application is None or application.status != ApplicationStatus.SCORING:
        await session.commit()  # отменили, пока считали: данные сохранены, решения нет
        return
    score = (
        await _save_score(
            session,
            application.id,
            company.id,
            today,
            features,
            scored,
            checks,
            hard_stop,
            latency_ms,
        )
        if scored
        else None
    )
    await _save_decision(
        session, application.id, score, decision, data, features, scored, checks
    )
    application.decided_at = datetime.now(UTC)
    target = _STATUS.get(decision.outcome, ApplicationStatus.MANUAL_REVIEW)
    comment = _COMMENT.get(decision.outcome, "Заявку рассмотрит специалист")
    if decision.reasons and decision.outcome != APPROVED:
        comment += ". Причина: " + texts.reason_text(decision.reasons[0]).lower()
    await transition(session, application, target, comment)
    await session.commit()


async def _save_decision(
    session: AsyncSession,
    application_id: uuid.UUID,
    score: ScoreResult | None,
    decision: Decision,
    data: CompanyData,
    features: dict,
    scored: tuple[ModelChoice, ScoreOutcome] | None,
    checks: list[StopCheck],
) -> None:
    offer = decision.offer
    coverage = dscr(data.income, data.payments) if data.income is not None else None
    details = {
        "outcome": decision.outcome,
        "offers": [_offer_json(o) for o in decision.offers],
        "acceptedOffer": None,  # индекс варианта, который принял клиент
        "alternatives": [_offer_json(o) for o in decision.alternatives],
        "hints": decision.hints,
        "inputs": {
            "income": float(data.income) if data.income is not None else None,
            "payments": float(data.payments),
            "ownPayments": float(data.own_payments),
            "dscr": float(coverage) if coverage is not None else None,
            "stopFactors": [
                {"code": c.code, "triggered": c.triggered, "details": c.details}
                for c in checks
            ],
            "features": features,
        },
        "model": (
            {
                "segment": scored[0].segment_code,
                "name": scored[0].model.model_name,
                "version": scored[0].model.version,
                "pd": scored[1].pd,
            }
            if scored
            else None
        ),
    }
    expires = datetime.now(UTC) + timedelta(days=OFFER_VALID_DAYS) if offer else None
    await decisions_repo.add_decision(
        session,
        CreditDecision(
            application_id=application_id,
            score_result_id=score.id if score else None,
            decision=_DECISION_TYPE.get(decision.outcome, DecisionType.MANUAL_REVIEW),
            approved_amount=offer.amount if offer else None,
            approved_term_months=offer.term_months if offer else None,
            rate=offer.rate if offer else None,
            reason_codes=decision.reasons,
            offer_expires_at=expires,
            details=details,
        ),
    )


async def send_to_manual_review(
    session: AsyncSession, application_id: uuid.UUID, error: str
) -> None:
    """Конвейер не справился после всех попыток — заявку смотрит специалист."""
    application = await applications_repo.lock_application(session, application_id)
    if application is None:
        return
    comment = (
        "Техническая ошибка при автоматической проверке — заявку рассмотрит специалист"
    )
    if application.status == ApplicationStatus.SUBMITTED:
        await transition(session, application, ApplicationStatus.SCORING, comment)
    if application.status != ApplicationStatus.SCORING:
        return
    await decisions_repo.add_decision(
        session,
        CreditDecision(
            application_id=application.id,
            decision=DecisionType.MANUAL_REVIEW,
            reason_codes=["SOURCE_ERROR"],
            details={"hints": texts.hints(["SOURCE_ERROR"]), "error": error[:500]},
        ),
    )
    await transition(session, application, ApplicationStatus.MANUAL_REVIEW, comment)
