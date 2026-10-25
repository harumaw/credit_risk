"""Кабинет: заявки на кредит — продукты, отправка анкеты, карточка с решением, действия клиента.

Отправка ставит заявку в `submitted` и кладёт задачу в очередь; решение принимает конвейер
(`services/pipeline.py`) в воркере. Статус меняется только через `transition`
(автомат `credit/statuses.py`), каждый переход пишется в историю.
"""

import hashlib
import secrets
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.credit import reasons as texts
from app.credit.exposure import fits_dscr, maturity_date, own_payments
from app.credit.statuses import FINAL, check_transition
from app.enums import ApplicationStatus, ConsentType, DecisionType
from app.exceptions import ConflictError, FieldValueError, NotFoundError
from app.models import (
    ApplicationStatusHistory,
    Company,
    Consent,
    CreditDecision,
    CreditProduct,
    Loan,
    LoanApplication,
    ScoreResult,
)
from app.repositories import application as applications_repo
from app.repositories import company as companies_repo
from app.repositories import decision as decisions_repo
from app.repositories import scoring as scoring_repo
from app.repositories import task as tasks_repo
from app.types import (
    Alternative,
    Application,
    ApplicationCreate,
    ApplicationDetails,
    ApplicationEvent,
    CreditProductRead,
    Decision,
    DecisionReason,
    Offer,
    Rating,
    SignCode,
)

CONSENT_TEXT_VERSION = "2026-10"
PROCESS_TASK = "process_application"
SIGN_CODE_TTL = timedelta(minutes=5)
SIGN_CODE_ATTEMPTS = 5  # неверных вводов, потом код сгорает (как SMS-код в банке)

# Статус в БД → статус и подпись для клиента
_CLIENT_STATUS: dict[ApplicationStatus, tuple[str, str]] = {
    ApplicationStatus.DRAFT: ("draft", "Черновик"),
    ApplicationStatus.SUBMITTED: ("submitted", "Заявка отправлена"),
    ApplicationStatus.DATA_COLLECTION: ("checking", "Собираем данные"),
    ApplicationStatus.SCORING: ("checking", "Оцениваем заявку"),
    ApplicationStatus.MANUAL_REVIEW: ("checking", "На рассмотрении у специалиста"),
    ApplicationStatus.APPROVED: ("approved", "Одобрено"),
    ApplicationStatus.OFFER_ACCEPTED: ("signing", "Подписание"),
    ApplicationStatus.CONTRACT_SIGNED: ("signing", "Договор подписан"),
    ApplicationStatus.ISSUED: ("issued", "Кредит выдан"),
    ApplicationStatus.DECLINED: ("rejected", "Отказ"),
    ApplicationStatus.CANCELLED: ("cancelled", "Заявка отменена"),
}
_NOTE = {
    "draft": "Заявка не отправлена — заполните и отправьте анкету",
    "submitted": "Заявка отправлена. Решение появится здесь — мы сообщим в кабинете",
    "checking": "Банк проверяет данные компании",
    "counter_offer": "Банк готов выдать кредит на других условиях — посмотрите предложение",
    "approved": "Банк одобрил заявку — примите условия",
    "signing": "Подпишите договор кодом — деньги придут сразу после подписания",
    "issued": "Деньги перечислены на счёт",
    "rejected": "По заявке принято отрицательное решение",
    "cancelled": "Вы отказались от кредита — можно подать новую заявку",
}
_OUTCOME = {
    DecisionType.APPROVE: "approved",
    DecisionType.COUNTER_OFFER: "counter_offer",
    DecisionType.DECLINE: "declined",
    DecisionType.MANUAL_REVIEW: "manual_review",
}


def _rub(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _company_name(company: Company) -> str:
    return company.short_name or company.full_name


def _product(p: CreditProduct) -> CreditProductRead:
    return CreditProductRead(
        code=p.code,
        name=p.name,
        kind=p.product_type.value,
        min_amount=_rub(p.min_amount) or 0,
        max_amount=_rub(p.max_amount) or 0,
        min_term_months=p.min_term_months or 1,
        max_term_months=p.max_term_months or 1,
        rate=float(p.base_rate or 0),
    )


def _client_status(status: ApplicationStatus, counter: bool) -> tuple[str, str]:
    """Контрпредложение в БД — approved; клиенту показываем его отдельно."""
    if status == ApplicationStatus.APPROVED and counter:
        return "counter_offer", "Предложены другие условия"
    return _CLIENT_STATUS[status]


_WITH_TERMS = (DecisionType.APPROVE, DecisionType.COUNTER_OFFER)


def _terms(d: CreditDecision | None) -> dict:
    """Условия из решения для карточки заявки: принятый вариант, до выбора — первый."""
    if d is None or d.decision not in _WITH_TERMS:
        return {}
    offers = _offers(d)
    chosen = (d.details or {}).get("acceptedOffer")
    top = offers[chosen if chosen is not None else 0] if offers else None
    if top is None:
        return {}
    return {
        "approved_amount": top["amount"],
        "approved_term_months": top["termMonths"],
        "approved_rate": top["rate"],
        "approved_monthly_payment": top["monthlyPayment"],
    }


def _application(
    a: LoanApplication,
    company: Company,
    product: CreditProduct,
    decision: CreditDecision | None = None,
) -> Application:
    counter = decision is not None and decision.decision == DecisionType.COUNTER_OFFER
    status = _client_status(a.status, counter)[0]
    return Application(
        id=a.id,
        number=a.number,
        company_id=company.id,
        company_name=_company_name(company),
        created_at=a.created_at.date(),
        product=product.name,
        product_code=product.code,
        amount=_rub(a.requested_amount),
        term_months=a.requested_term_months,
        purpose=a.purpose,
        status=status,
        note=_NOTE.get(status, ""),
        **_terms(decision),
    )


def _check_conditions(data: ApplicationCreate, product: CreditProduct) -> None:
    """Сумма и срок — в пределах условий продукта."""
    lo, hi = _rub(product.min_amount), _rub(product.max_amount)
    if (lo is not None and data.amount < lo) or (hi is not None and data.amount > hi):
        raise FieldValueError(
            "amount",
            f"Сумма по этому продукту — от {lo:,} до {hi:,} ₽".replace(",", " "),
        )
    t_lo, t_hi = product.min_term_months, product.max_term_months
    if (t_lo is not None and data.term_months < t_lo) or (
        t_hi is not None and data.term_months > t_hi
    ):
        raise FieldValueError(
            "termMonths", f"Срок по этому продукту — от {t_lo} до {t_hi} мес"
        )


def _offers(d: CreditDecision) -> list[dict]:
    return (d.details or {}).get("offers", [])


def _decision(
    d: CreditDecision, score: ScoreResult | None, rating: Rating | None = None
) -> Decision:
    details = d.details or {}
    offers = _offers(d)
    chosen = details.get("acceptedOffer")
    top = offers[chosen if chosen is not None else 0] if offers else None
    return Decision(
        outcome=_OUTCOME[d.decision],
        amount=_rub(d.approved_amount),
        term_months=d.approved_term_months,
        rate=float(d.rate) if d.rate is not None else None,
        monthly_payment=top["monthlyPayment"] if top else None,
        offers=[
            Offer(
                amount=o["amount"],
                term_months=o["termMonths"],
                rate=o["rate"],
                monthly_payment=o["monthlyPayment"],
            )
            for o in offers
        ],
        accepted_offer_index=chosen,
        grade=score.grade if score else None,
        reasons=[
            DecisionReason(code=code, text=texts.reason_text(code))
            for code in d.reason_codes or []
        ],
        alternatives=[Alternative(**a) for a in details.get("alternatives", [])],
        hints=details.get("hints", []),
        decided_at=d.decided_at,
        rating=rating,
    )


NEXT_GRADE_CLOSE = 10  # баллов до границы рейтинга выше — «немного» (PDO 20: шансы ×1,4)


async def _rating(session: AsyncSession, score: ScoreResult | None) -> Rating | None:
    """Расшифровка рейтинга словами: место на шкале, что помогло, что мешает, советы.

    Баллы, границы шкалы и PD остаются на сервере — клиенту только формулировки.
    """
    if score is None or score.total_score is None:
        return None
    grades = await scoring_repo.model_grades(session, score.model_version_id)
    bins = await scoring_repo.model_bins(session, score.model_version_id)
    points = await decisions_repo.score_points(session, score.id)
    best: dict[str, float] = {}
    for b in bins:
        best[b.feature_code] = max(best.get(b.feature_code, float(b.points)), float(b.points))
    lost = {code: best[code] - got for code, got in points.items() if code in best}
    weak = sorted((c for c, x in lost.items() if x > 0.5), key=lost.__getitem__, reverse=True)
    strong = [c for c, x in lost.items() if x <= 0.5]

    total = float(score.total_score)
    upper = [float(g.score_from) for g in grades if float(g.score_from) > total]
    gap = min(upper) - total if upper else None
    return Rating(
        grade=score.grade,
        scale=[g.grade for g in grades],
        next_grade="top" if gap is None else "close" if gap <= NEXT_GRADE_CLOSE else "far",
        strengths=[t for c in strong if (t := texts.strength_text(c))],
        weaknesses=list(dict.fromkeys(texts.reason_text(c) for c in weak if c in texts.REASONS)),
        improve=texts.hints(weak[:5]),
        keep=texts.keep_hints(strong),
    )


def _event(h: ApplicationStatusHistory, counter: bool) -> ApplicationEvent:
    status, label = _client_status(h.to_status, counter)
    return ApplicationEvent(
        status=status, label=label, at=h.changed_at, comment=h.comment
    )


async def _latest(
    session: AsyncSession, application_id: uuid.UUID
) -> CreditDecision | None:
    latest = await decisions_repo.latest_decision(session, application_id)
    return latest[0] if latest else None


async def _is_counter(session: AsyncSession, application_id: uuid.UUID) -> bool:
    latest = await decisions_repo.latest_decision(session, application_id)
    return latest is not None and latest[0].decision == DecisionType.COUNTER_OFFER


# --- Чтение -----------------------------------------------------------------


async def list_products(session: AsyncSession) -> list[CreditProductRead]:
    return [_product(p) for p in await applications_repo.list_active_products(session)]


async def list_applications(
    session: AsyncSession, user_id: uuid.UUID
) -> list[Application]:
    rows = await applications_repo.list_user_applications(session, user_id)
    return [_application(*row, await _latest(session, row[0].id)) for row in rows]


async def application_details(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> ApplicationDetails:
    row = await applications_repo.get_user_application(session, user_id, application_id)
    if row is None:
        raise NotFoundError  # чужая заявка неотличима от несуществующей
    latest = await decisions_repo.latest_decision(session, application_id)
    counter = latest is not None and latest[0].decision == DecisionType.COUNTER_OFFER
    history = await applications_repo.list_history(session, application_id)
    return ApplicationDetails(
        **_application(*row, latest[0] if latest else None).model_dump(),
        history=[_event(h, counter) for h in history],
        decision=_decision(*latest, await _rating(session, latest[1]))
        if latest
        else None,
    )


# --- Переходы ---------------------------------------------------------------


async def transition(
    session: AsyncSession,
    application: LoanApplication,
    target: ApplicationStatus,
    comment: str,
    user_id: uuid.UUID | None = None,
) -> None:
    """Единственная точка смены статуса: проверка автомата + запись в историю."""
    check_transition(application.status, target)  # TransitionError → 409
    await applications_repo.add_history(
        session,
        ApplicationStatusHistory(
            application_id=application.id,
            from_status=application.status,
            to_status=target,
            changed_by_user_id=user_id,
            comment=comment,
        ),
    )
    application.status = target


async def _locked_own(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> LoanApplication:
    own = await applications_repo.get_user_application(session, user_id, application_id)
    if own is None:
        raise NotFoundError
    application = await applications_repo.lock_application(session, application_id)
    assert application is not None
    return application


async def accept(
    session: AsyncSession,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    offer_index: int = 0,
) -> ApplicationDetails:
    """Клиент выбирает вариант решения; условия фиксируются в решении."""
    application = await _locked_own(session, user_id, application_id)
    check_transition(application.status, ApplicationStatus.OFFER_ACCEPTED)
    latest = await decisions_repo.latest_decision(session, application_id)
    offers = _offers(latest[0]) if latest else []
    if not 0 <= offer_index < len(offers):
        raise FieldValueError("offerIndex", "Такого варианта в решении нет")
    decision, chosen = latest[0], offers[offer_index]  # type: ignore[index]
    if decision.offer_expires_at and decision.offer_expires_at < datetime.now(UTC):
        raise ConflictError("Срок предложения истёк — подайте новую заявку")
    await _check_still_affordable(session, application, decision, chosen)
    decision.approved_amount = Decimal(chosen["amount"])
    decision.approved_term_months = chosen["termMonths"]
    decision.rate = Decimal(str(chosen["rate"]))
    decision.offer_accepted_at = datetime.now(UTC)
    decision.details = {**(decision.details or {}), "acceptedOffer": offer_index}
    await transition(
        session,
        application,
        ApplicationStatus.OFFER_ACCEPTED,
        f"Клиент принял условия: {chosen['amount']:,} ₽ на {chosen['termMonths']} мес".replace(
            ",", " "
        ),
        user_id,
    )
    await session.commit()
    return await application_details(session, user_id, application_id)


async def _check_still_affordable(
    session: AsyncSession,
    application: LoanApplication,
    decision: CreditDecision,
    chosen: dict,
) -> None:
    """Предложение считали на долгах в момент решения. Если с тех пор компания приняла
    или получила другой наш кредит, платёж мог перестать помещаться в DSCR — проверяем
    заново. Компания под блокировкой: параллельные принятия по её заявкам идут по очереди.
    """
    await applications_repo.lock_company(session, application.company_id)
    inputs = (decision.details or {}).get("inputs") or {}
    income = inputs.get("income")
    # платежи по чужим кредитам (БКИ) на момент решения + наши обязательства сейчас
    external = Decimal(str(inputs.get("payments") or 0)) - Decimal(
        str(inputs.get("ownPayments") or 0)
    )
    own = own_payments(
        await applications_repo.own_credits(
            session, [application.company_id], exclude_application_id=application.id
        )
    )
    if not fits_dscr(
        Decimal(str(income)) if income is not None else None,
        external + own,
        Decimal(chosen["monthlyPayment"]),
    ):
        raise ConflictError(
            "Условия больше не действуют: после решения по этой заявке компания взяла "
            "другой кредит, и платёж уже не помещается в доход. Подайте новую заявку — "
            "посчитаем лимит с учётом нового долга"
        )


def _code_hash(application_id: uuid.UUID, code: str) -> str:
    return hashlib.sha256(f"{application_id}:{code}".encode()).hexdigest()


async def sign_code(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> SignCode:
    """Имитация SMS с кодом подписи: код — в ответе, в БД только хэш и срок жизни."""
    application = await _locked_own(session, user_id, application_id)
    check_transition(application.status, ApplicationStatus.CONTRACT_SIGNED)
    code = f"{secrets.randbelow(10**6):06d}"
    expires = datetime.now(UTC) + SIGN_CODE_TTL
    application.sign_code_hash = _code_hash(application.id, code)
    application.sign_code_expires_at = expires
    application.sign_code_attempts = 0
    await session.commit()
    return SignCode(code=code, expires_at=expires)


async def sign(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID, code: str
) -> ApplicationDetails:
    application = await _locked_own(session, user_id, application_id)
    check_transition(application.status, ApplicationStatus.CONTRACT_SIGNED)
    expires = application.sign_code_expires_at
    if application.sign_code_hash is None or expires is None:
        raise FieldValueError("code", "Сначала запросите код")
    if expires < datetime.now(UTC):
        raise FieldValueError("code", "Код устарел — запросите новый")
    if not secrets.compare_digest(
        application.sign_code_hash, _code_hash(application.id, code)
    ):
        application.sign_code_attempts += 1
        if application.sign_code_attempts < SIGN_CODE_ATTEMPTS:
            await session.commit()
            raise FieldValueError("code", "Неверный код")
        application.sign_code_hash = None  # перебор не пройдёт: нужен новый код
        application.sign_code_expires_at = None
        await session.commit()
        raise FieldValueError(
            "code", "Код введён неверно 5 раз и больше не действует — запросите новый"
        )
    application.sign_code_hash = None
    application.sign_code_expires_at = None
    await transition(
        session,
        application,
        ApplicationStatus.CONTRACT_SIGNED,
        "Договор подписан кодом из SMS",
        user_id,
    )
    await transition(
        session, application, ApplicationStatus.ISSUED, "Деньги перечислены на счёт"
    )
    await _book_loan(session, application)
    await session.commit()
    return await application_details(session, user_id, application_id)


async def _book_loan(session: AsyncSession, application: LoanApplication) -> None:
    """Выданный кредит — в портфель: дальше он входит в долговую нагрузку компании."""
    latest = await decisions_repo.latest_decision(session, application.id)
    assert latest is not None
    decision = latest[0]
    issued = datetime.now(UTC).date()
    term = decision.approved_term_months or application.requested_term_months or 1
    await applications_repo.add_loan(
        session,
        Loan(
            application_id=application.id,
            company_id=application.company_id,
            contract_number=f"КД-{application.number}",
            amount=decision.approved_amount or Decimal(0),
            rate=decision.rate or Decimal(0),
            term_months=term,
            issued_at=issued,
            maturity_date=maturity_date(issued, term),
        ),
    )


async def cancel(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> ApplicationDetails:
    application = await _locked_own(session, user_id, application_id)
    await transition(
        session,
        application,
        ApplicationStatus.CANCELLED,
        "Клиент отказался от кредита",
        user_id,
    )
    await session.commit()
    return await application_details(session, user_id, application_id)


# --- События (SSE) ----------------------------------------------------------


async def ensure_visible(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> None:
    if (
        await applications_repo.get_user_application(session, user_id, application_id)
        is None
    ):
        raise NotFoundError


async def events(
    session: AsyncSession,
    application_id: uuid.UUID,
    poll_seconds: float,
    max_polls: int,
    sleep: Callable[[float], Awaitable[None]],
) -> AsyncIterator[ApplicationEvent | None]:
    """Вся история, затем новые смены статуса; None — событий за опрос не было (пинг).

    Поток кончается после финального статуса или через max_polls опросов (клиент
    переподключится). Доступ проверяет `ensure_visible` до вызова.
    """
    last_id = 0
    for _ in range(max_polls):
        rows = await applications_repo.history_after(session, application_id, last_id)
        if rows:
            counter = await _is_counter(session, application_id)
            for h in rows:
                yield _event(h, counter)
            last_id = rows[-1].id
            if rows[-1].to_status in FINAL:
                return
        else:
            yield None
        await session.commit()  # закрыть снимок: следующий опрос увидит коммиты воркера
        await sleep(poll_seconds)


# --- Отправка ---------------------------------------------------------------


async def submit(
    session: AsyncSession,
    user_id: uuid.UUID,
    data: ApplicationCreate,
    idempotency_key: str | None = None,
) -> ApplicationDetails:
    if idempotency_key:
        existing = await applications_repo.get_by_idempotency_key(
            session, user_id, idempotency_key
        )
        if existing is not None:  # повтор той же отправки — та же заявка
            return await application_details(session, user_id, existing.id)
    company = await companies_repo.get_company(session, data.company_id)
    if (
        company is None
        or await companies_repo.get_link(session, user_id, company.id) is None
    ):
        raise FieldValueError("companyId", "Выберите компанию из своего кабинета")
    product = await applications_repo.get_active_product(session, data.product_code)
    if product is None:
        raise FieldValueError("productCode", "Такого продукта нет — выберите из списка")
    _check_conditions(data, product)

    now = datetime.now(UTC)
    application = LoanApplication(
        number=await applications_repo.next_number(session),
        company_id=company.id,
        applicant_user_id=user_id,
        product_id=product.id,
        requested_amount=Decimal(data.amount),
        requested_term_months=data.term_months,
        purpose=data.purpose,
        form_step=1,
        status=ApplicationStatus.SUBMITTED,
        submitted_at=now,
        idempotency_key=idempotency_key,
    )
    history = ApplicationStatusHistory(
        from_status=None,
        to_status=ApplicationStatus.SUBMITTED,
        changed_by_user_id=user_id,
        comment="Анкета заполнена и отправлена клиентом",
    )
    consents = [
        Consent(
            user_id=user_id,
            company_id=company.id,
            consent_type=kind,
            text_version=CONSENT_TEXT_VERSION,
            signed_at=now,
        )
        for kind in (ConsentType.PERSONAL_DATA, ConsentType.BKI_REQUEST)
    ]
    try:
        application = await applications_repo.add_application(
            session, application, history, consents
        )
        await tasks_repo.enqueue(session, PROCESS_TASK, application.id)
        await session.commit()
    except IntegrityError:
        # Одновременный повтор с тем же ключом: вставка ждёт первую на UNIQUE и падает —
        # отдаём заявку первой отправки, как при обычном повторе
        await session.rollback()
        existing = idempotency_key and await applications_repo.get_by_idempotency_key(
            session, user_id, idempotency_key
        )
        if not existing:
            raise
        return await application_details(session, user_id, existing.id)
    return await application_details(session, user_id, application.id)
