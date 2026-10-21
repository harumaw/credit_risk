"""Кабинет: компании пользователя — поиск по ИНН, добавление, сводки по компании и по группе."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.credit.forecast import linear_forecast
from app.credit.limit import dscr, dscr_limit
from app.enums import (
    CompanyRole,
    CompanyStatus,
    DataSource,
    FetchStatus,
    LinkStatus,
    MspCategory,
    TaxRegime,
    ZskZone,
)
from app.exceptions import AlreadyExistsError, ForbiddenError, NotFoundError
from app.integrations.egrul import EgrulRecord
from app.integrations.registry import Sources
from app.models import Company, DataFetch, User
from app.repositories import company as companies_repo
from app.repositories import external_data as data_repo
from app.repositories import user as users_repo
from app.services import company_data
from app.settings import settings
from app.types import (
    Check,
    CompanyAdded,
    CompanyBrief,
    CompanyCard,
    CompanyLookup,
    CompanySummary,
    CreditLimit,
    ForecastPoint,
    GroupCompany,
    GroupSummary,
    Loan,
    Metrics,
    MonthPoint,
    NextPayment,
    Okved,
    SourceStatus,
)

HISTORY_MONTHS = 12
FORECAST_MONTHS = 3

_STATUS_TEXT = {
    CompanyStatus.ACTIVE: "Действует",
    CompanyStatus.REORGANIZING: "Реорганизация",
    CompanyStatus.LIQUIDATING: "Ликвидация",
    CompanyStatus.LIQUIDATED: "Ликвидирована",
    CompanyStatus.BANKRUPT: "Банкротство",
}
_MSP_TEXT = {
    MspCategory.MICRO: "Микро",
    MspCategory.SMALL: "Малое",
    MspCategory.MEDIUM: "Среднее",
    MspCategory.NOT_MSP: "Не МСП",
}
_REGIME_TEXT = {
    TaxRegime.OSNO: "Общий режим",
    TaxRegime.USN_INCOME: "УСН «доходы»",
    TaxRegime.USN_INCOME_EXPENSE: "УСН «доходы минус расходы»",
    TaxRegime.ESHN: "ЕСХН",
    TaxRegime.PSN: "Патент",
    TaxRegime.AUSN: "АУСН",
}
_ZSK_TEXT = {ZskZone.GREEN: "Зелёная", ZskZone.YELLOW: "Жёлтая", ZskZone.RED: "Красная"}
MSK = timezone(timedelta(hours=3))
NEEDS_STATEMENT = "Счёт открыт в другом банке — загрузите выписку за 12 месяцев"


def _today() -> date:
    return datetime.now(MSK).date()


def _rub(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _fmt_rub(value: Decimal) -> str:
    return f"{_rub(value):,}".replace(",", " ") + " ₽"


def _change_pct(current: Decimal, previous: Decimal) -> float | None:
    if previous <= 0:
        return None
    return round(float((current - previous) / previous * 100), 1)


def _kind(company: Company) -> str:
    return "ip" if len(company.inn) == 12 else "ul"


def _name(company: Company) -> str:
    return company.short_name or company.full_name


def _norm_fio(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def _user_fio(user: User) -> str:
    return " ".join(p for p in (user.last_name, user.first_name, user.middle_name) if p)


def _can_add(user: User, record: EgrulRecord) -> tuple[bool, str | None]:
    """Добавить можно только свою компанию: руководитель в ЕГРЮЛ = ФИО + ИНН пользователя."""
    head = record.director
    if head is None:
        return False, "В реестре не указан руководитель"
    if head.inn != user.inn_fl or _norm_fio(head.full_name) != _norm_fio(
        _user_fio(user)
    ):
        return (
            False,
            "Руководитель в реестре — другой человек. Заявку подаёт только сам руководитель",
        )
    return True, None


async def _user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await users_repo.get_user_by_id(session, user_id)
    if user is None:
        raise NotFoundError
    return user


async def _fetch_registry(
    session: AsyncSession, sources: Sources, inn: str
) -> tuple[Company, EgrulRecord]:
    fetched = await sources.egrul.fetch(inn)  # ошибки источника — наверх, в роут
    company = await company_data.save_registry_card(session, fetched)
    return company, fetched.data


def _source_status(fetch: DataFetch) -> SourceStatus:
    return SourceStatus(
        source=fetch.source,
        label=company_data.SOURCE_LABELS.get(fetch.source, fetch.source.value),
        status=fetch.status,
        received_at=fetch.received_at,
        error=fetch.error,
    )


async def lookup(
    session: AsyncSession, sources: Sources, user_id: uuid.UUID, inn: str
) -> CompanyLookup:
    user = await _user(session, user_id)
    company, record = await _fetch_registry(session, sources, inn)
    already = await companies_repo.get_link(session, user.id, company.id) is not None
    can_add, reason = _can_add(user, record)
    if already:
        can_add, reason = False, "Компания уже есть в кабинете"
    await session.commit()
    okved_main = (
        Okved(code=record.okved_main[0], name=record.okved_main[1], is_main=True)
        if record.okved_main
        else None
    )
    return CompanyLookup(
        company_id=company.id,
        inn=company.inn,
        name=_name(company),
        kind=_kind(company),
        status=company.status,
        registration_date=company.registration_date,
        okved_main=okved_main,
        director_name=record.director.full_name if record.director else None,
        can_add=can_add,
        reason=reason,
        already_added=already,
    )


async def add(
    session: AsyncSession, sources: Sources, user_id: uuid.UUID, inn: str
) -> CompanyAdded:
    user = await _user(session, user_id)
    company, record = await _fetch_registry(session, sources, inn)
    if await companies_repo.get_link(session, user.id, company.id) is not None:
        await session.rollback()
        raise AlreadyExistsError("company")
    can_add, reason = _can_add(user, record)
    if not can_add:
        await session.commit()  # карточку из реестра сохраняем, связь — нет
        raise ForbiddenError(reason or "Нельзя добавить компанию")

    await companies_repo.create_link(
        session,
        user_id=user.id,
        company_id=company.id,
        role=CompanyRole.DIRECTOR,
        status=LinkStatus.CONFIRMED,
    )
    fetches = await company_data.collect(session, sources, company)
    await session.commit()
    months = await data_repo.monthly_totals(session, [company.id])
    statuses = [
        SourceStatus(
            source=sources.egrul.source,
            label=company_data.SOURCE_LABELS[sources.egrul.source],
            status=FetchStatus.SUCCESS,
            received_at=company.registry_synced_at,
            error=None,
        ),
        *(_source_status(f) for f in fetches),
    ]
    return CompanyAdded(
        company=_brief(company, has_turnovers=bool(months)), sources=statuses
    )


def _brief(company: Company, *, has_turnovers: bool) -> CompanyBrief:
    return CompanyBrief(
        id=company.id,
        inn=company.inn,
        name=_name(company),
        kind=_kind(company),
        msp_category=company.msp_category,
        needs_statement=not has_turnovers,
    )


async def list_companies(
    session: AsyncSession, user_id: uuid.UUID
) -> list[CompanyBrief]:
    rows = await companies_repo.list_user_companies(session, user_id)
    ids = [c.id for c, _ in rows]
    with_turnovers = {
        m.company_id for m in await data_repo.monthly_totals(session, ids)
    }
    return [_brief(c, has_turnovers=c.id in with_turnovers) for c, _ in rows]


async def _own_company(
    session: AsyncSession, user_id: uuid.UUID, company_id: uuid.UUID
) -> Company:
    company = await companies_repo.get_company(session, company_id)
    if (
        company is None
        or await companies_repo.get_link(session, user_id, company_id) is None
    ):
        raise NotFoundError  # чужая компания неотличима от несуществующей
    return company


# --- Сводка по компании -----------------------------------------------------


def _income(months: list[data_repo.MonthTotals]) -> Decimal | None:
    recent = months[-HISTORY_MONTHS:]
    if not recent:
        return None
    return sum((m.inflow - m.outflow for m in recent), Decimal(0)) / len(recent)


def _limit(
    income: Decimal | None,
    payments: Decimal,
    *,
    active: bool,
    reason: str | None = None,
) -> CreditLimit:
    term, rate = settings.PRELIMINARY_TERM_MONTHS, settings.PRELIMINARY_RATE_PCT
    if not active:
        return CreditLimit(
            amount=None,
            term_months=term,
            rate_pct=float(rate),
            needs_statement=False,
            reason=reason or "Компания не действует",
        )
    if income is None:
        return CreditLimit(
            amount=None,
            term_months=term,
            rate_pct=float(rate),
            needs_statement=True,
            reason=reason or NEEDS_STATEMENT,
        )
    return CreditLimit(
        amount=_rub(dscr_limit(income, payments, rate, term)),
        term_months=term,
        rate_pct=float(rate),
        needs_statement=False,
        reason=reason,
    )


async def _checks(
    session: AsyncSession, company: Company, fetched: set[DataSource]
) -> list[Check]:
    registry = "Статус в ЕГРИП" if _kind(company) == "ip" else "Статус в ЕГРЮЛ"
    checks = [
        Check(
            code="registry_status",
            label=registry,
            value=_STATUS_TEXT[company.status],
            ok=company.status == CompanyStatus.ACTIVE,
        )
    ]

    debt = await data_repo.latest_tax_debt(session, company.id)
    if debt is None:
        checks.append(
            Check(code="tax_debt", label="Налоговый долг", value="Нет данных", ok=None)
        )
    else:
        total = debt.tax_debt + debt.penalties + debt.fines
        checks.append(
            Check(
                code="tax_debt",
                label="Налоговый долг",
                value="Нет" if total == 0 else _fmt_rub(total),
                ok=total == 0,
            )
        )

    if DataSource.FSSP in fetched:
        count, remaining = await data_repo.active_enforcements(session, company.id)
        checks.append(
            Check(
                code="fssp",
                label="Приставы (ФССП)",
                value="Нет производств"
                if count == 0
                else f"{count} на {_fmt_rub(remaining)}",
                ok=count == 0,
            )
        )
    else:
        checks.append(
            Check(code="fssp", label="Приставы (ФССП)", value="Нет данных", ok=None)
        )

    if DataSource.EFRSB in fetched:
        events = await data_repo.count_bankruptcy_events(session, company.id)
        checks.append(
            Check(
                code="bankruptcy",
                label="Банкротства",
                value="Нет" if events == 0 else f"Сообщений: {events}",
                ok=events == 0,
            )
        )
    else:
        checks.append(
            Check(code="bankruptcy", label="Банкротства", value="Нет данных", ok=None)
        )

    zsk = await data_repo.latest_zsk(session, company.id)
    checks.append(
        Check(
            code="zsk",
            label="Зона риска ЦБ",
            value=_ZSK_TEXT[zsk.zone] if zsk else "Нет данных",
            ok=zsk.zone == ZskZone.GREEN if zsk else None,
        )
    )

    if DataSource.BKI in fetched:
        worst = await data_repo.worst_past_dpd(session, company.id)
        open_ = await data_repo.open_obligations(session, [company.id], _today())
        overdue = sum((o.overdue for o in open_), Decimal(0))
        if overdue > 0:
            value, ok = f"Текущая просрочка {_fmt_rub(overdue)}", False
        elif worst > 0:
            value, ok = f"Была просрочка до {worst} дн.", False
        else:
            value, ok = "Без просрочек", True
        checks.append(
            Check(code="credit_history", label="Кредитная история", value=value, ok=ok)
        )
    else:
        checks.append(
            Check(
                code="credit_history",
                label="Кредитная история",
                value="Нет данных",
                ok=None,
            )
        )

    if company.tax_regime:
        checks.append(
            Check(
                code="tax_regime",
                label="Налоговый режим",
                value=_REGIME_TEXT[company.tax_regime],
                ok=None,
            )
        )
    if company.msp_category:
        checks.append(
            Check(
                code="msp",
                label="Категория МСП",
                value=_MSP_TEXT[company.msp_category],
                ok=None,
            )
        )
    if company.headcount is not None:
        checks.append(
            Check(
                code="headcount",
                label="Численность",
                value=str(company.headcount),
                ok=None,
            )
        )
    return checks


async def company_summary(
    session: AsyncSession, user_id: uuid.UUID, company_id: uuid.UUID
) -> CompanySummary:
    company = await _own_company(session, user_id, company_id)
    fetches = await data_repo.latest_fetches(session, company.id)
    fetched = {f.source for f in fetches if f.status == FetchStatus.SUCCESS}
    months = await data_repo.monthly_totals(session, [company.id])
    loans = await data_repo.open_obligations(session, [company.id], _today())

    recent = months[-HISTORY_MONTHS:]
    previous = months[-2 * HISTORY_MONTHS : -HISTORY_MONTHS]
    inflow_12m = sum((m.inflow for m in recent), Decimal(0)) if recent else None
    income = _income(months)
    payments = sum((o.next_payment for o in loans), Decimal(0))

    forecast = []
    if recent:
        inflow_fc = linear_forecast(
            [m.inflow for m in recent], recent[-1].month, FORECAST_MONTHS
        )
        balance_fc = linear_forecast(
            [m.closing_balance for m in recent], recent[-1].month, FORECAST_MONTHS
        )
        forecast = [
            ForecastPoint(
                month=i.month,
                inflow=_rub(i.value),
                inflow_lower=_rub(i.lower),
                inflow_upper=_rub(i.upper),
                closing_balance=_rub(b.value),
            )
            for i, b in zip(inflow_fc, balance_fc, strict=True)
        ]

    metrics = Metrics(
        inflow_12m=_rub(inflow_12m),
        inflow_12m_change_pct=_change_pct(
            inflow_12m, sum((m.inflow for m in previous), Decimal(0))
        )
        if recent and len(previous) == HISTORY_MONTHS
        else None,
        inflow_last_month=_rub(recent[-1].inflow) if recent else None,
        inflow_last_month_change_pct=_change_pct(recent[-1].inflow, recent[-2].inflow)
        if len(recent) >= 2
        else None,
        avg_balance=_rub(
            sum((m.closing_balance for m in recent), Decimal(0)) / len(recent)
        )
        if recent
        else None,
        monthly_income=_rub(income),
        monthly_payments=_rub(payments),
        dscr=round(float(ratio), 2)
        if income is not None and (ratio := dscr(income, payments)) is not None
        else None,
    )

    okved = await companies_repo.list_company_okved(session, company.id)
    return CompanySummary(
        company=CompanyCard(
            id=company.id,
            inn=company.inn,
            ogrn=company.ogrn,
            kpp=company.kpp,
            name=_name(company),
            full_name=company.full_name,
            legal_form=company.legal_form,
            kind=_kind(company),
            status=company.status,
            registration_date=company.registration_date,
            region_code=company.region_code,
            address=company.legal_address,
            msp_category=company.msp_category,
            headcount=company.headcount,
            tax_regime=company.tax_regime,
            is_bank_client=bool(months),
        ),
        okved=[Okved(code=c, name=n, is_main=m) for c, n, m in okved],
        checks=await _checks(session, company, fetched),
        turnovers=[
            MonthPoint(
                month=m.month,
                inflow=_rub(m.inflow),
                outflow=_rub(m.outflow),
                closing_balance=_rub(m.closing_balance),
            )
            for m in recent
        ],
        forecast=forecast,
        metrics=metrics,
        loans=[
            Loan(
                lender=o.lender,
                product_type=o.product_type,
                outstanding=_rub(o.outstanding),
                monthly_payment=_rub(o.next_payment),
                next_payment_date=o.next_payment_date,
                overdue=_rub(o.overdue),
            )
            for o in loans
        ],
        limit=_limit(
            income,
            payments,
            active=company.status == CompanyStatus.ACTIVE,
            reason=None
            if company.status == CompanyStatus.ACTIVE
            else f"Компания не действует: {_STATUS_TEXT[company.status].lower()}",
        ),
        sources=[_source_status(f) for f in fetches],
    )


# --- Сводка по группе -------------------------------------------------------


async def group_summary(session: AsyncSession, user_id: uuid.UUID) -> GroupSummary:
    rows = await companies_repo.list_user_companies(session, user_id)
    companies = [c for c, _ in rows]
    ids = [c.id for c in companies]
    months = await data_repo.monthly_totals(session, ids)
    loans = await data_repo.open_obligations(session, ids, _today())

    by_company: dict[uuid.UUID, list[data_repo.MonthTotals]] = {}
    for m in months:
        by_company.setdefault(m.company_id, []).append(m)

    group_rows = []
    incomes = []
    for c in companies:
        own_months = by_company.get(c.id, [])
        own_loans = [o for o in loans if o.company_id == c.id]
        income = _income(own_months)
        if income is not None:
            incomes.append(income)
        group_rows.append(
            GroupCompany(
                id=c.id,
                inn=c.inn,
                name=_name(c),
                kind=_kind(c),
                msp_category=c.msp_category,
                inflow_last_month=_rub(own_months[-1].inflow) if own_months else None,
                debt=_rub(sum((o.outstanding for o in own_loans), Decimal(0))),
                monthly_payment=_rub(
                    sum((o.next_payment for o in own_loans), Decimal(0))
                ),
                needs_statement=not own_months,
            )
        )

    payments = sum((o.next_payment for o in loans), Decimal(0))
    missing = [r.name for r in group_rows if r.needs_statement]
    reason = None
    if missing and incomes:
        reason = f"Доход не учтён: {', '.join(missing)} — нужна выписка. После неё лимит может вырасти"
    limit = _limit(
        sum(incomes, Decimal(0)) if incomes else None,
        payments,
        active=True,
        reason=reason,
    )
    if missing and incomes:
        limit.needs_statement = True

    upcoming = [o for o in loans if o.next_payment_date is not None]
    nearest = min(upcoming, key=lambda o: o.next_payment_date, default=None)
    last_inflows = [
        r.inflow_last_month for r in group_rows if r.inflow_last_month is not None
    ]
    return GroupSummary(
        companies=group_rows,
        total_debt=_rub(sum((o.outstanding for o in loans), Decimal(0))),
        loans_count=len(loans),
        monthly_payments=_rub(payments),
        next_payment=NextPayment(
            date=nearest.next_payment_date,
            amount=_rub(nearest.next_payment),
            company_id=nearest.company_id,
            lender=nearest.lender,
        )
        if nearest
        else None,
        inflow_last_month=sum(last_inflows) if last_inflows else None,
        limit=limit,
    )
